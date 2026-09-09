"""Build a trainable Phase 5 manifest from provenance-preserving source records.

This module deliberately does not download daily visual mosaics and pretend they
are timestamped satellite observations.  It joins already-downloaded satellite
products (with their actual acquisition times) to IBTrACS New Delhi 3-minute
wind observations, then performs an event-level split.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WIND_CATEGORIES: tuple[tuple[str, float, float | None], ...] = (
    ("Depression", 31.0, 49.0),
    ("Deep Depression", 50.0, 61.0),
    ("Cyclonic Storm", 62.0, 87.0),
    ("Severe Cyclonic Storm", 88.0, 117.0),
    ("Very Severe Cyclonic Storm", 118.0, 166.0),
    ("Extremely Severe Cyclonic Storm", 167.0, 220.0),
    ("Super Cyclonic Storm", 221.0, None),
)
KT_TO_KMH = 1.852


class ManifestBuildError(ValueError):
    """Source data cannot safely produce a Phase 5 training manifest."""


@dataclass(frozen=True)
class BestTrackPoint:
    cyclone_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    wind_speed_kmh: float
    central_pressure_hpa: float | None


def _value(row: dict[str, str], *columns: str) -> str:
    for column in columns:
        value = (row.get(column) or "").strip()
        if value:
            return value
    return ""


def _timestamp(value: str, *, context: str) -> datetime:
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        try:
            parsed = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ManifestBuildError(f"{context} is not an ISO-8601 timestamp: {value!r}") from exc
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def category_for_wind_kmh(wind_speed_kmh: float) -> str | None:
    """Map a genuine IMD 3-minute wind speed to an IMD category."""
    for category, lower, upper in WIND_CATEGORIES:
        if wind_speed_kmh >= lower and (upper is None or wind_speed_kmh <= upper):
            return category
    return None


def _newdelhi_wind_knots(row: dict[str, str], row_number: int) -> float | None:
    direct = _value(row, "NEWDELHI_WIND", "NEW_WIND")
    if direct:
        return float(direct)
    # WMO wind is valid for the IMD scale only when its reporting agency is
    # explicitly New Delhi.  Do not silently substitute USA 1-minute winds.
    agency = _value(row, "WMO_AGENCY").lower().replace(" ", "")
    wmo_wind = _value(row, "WMO_WIND")
    if wmo_wind and agency in {"newdelhi", "imd"}:
        return float(wmo_wind)
    return None


def load_newdelhi_best_track(path: Path) -> list[BestTrackPoint]:
    """Load only North Indian Ocean positions with a 3-minute IMD-compatible wind."""
    if not path.is_file():
        raise ManifestBuildError(f"IBTrACS CSV does not exist: {path}")
    result: list[BestTrackPoint] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"SID", "ISO_TIME", "LAT", "LON"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ManifestBuildError(f"IBTrACS CSV is missing: {', '.join(sorted(missing))}")
        for row_number, row in enumerate(reader, start=2):
            try:
                wind_knots = _newdelhi_wind_knots(row, row_number)
            except ValueError as exc:
                raise ManifestBuildError(f"IBTrACS row {row_number} has an invalid wind value") from exc
            if wind_knots is None:
                continue
            try:
                wind_kmh = wind_knots * KT_TO_KMH
                category = category_for_wind_kmh(wind_kmh)
                if category is None:
                    continue
                pressure_value = _value(row, "NEWDELHI_PRES", "NEW_PRES")
                if not pressure_value and _value(row, "WMO_AGENCY").lower().replace(" ", "") in {"newdelhi", "imd"}:
                    pressure_value = _value(row, "WMO_PRES")
                result.append(BestTrackPoint(
                    cyclone_id=_value(row, "SID"), timestamp=_timestamp(_value(row, "ISO_TIME"), context=f"IBTrACS row {row_number}"),
                    latitude=float(_value(row, "LAT")), longitude=float(_value(row, "LON")), wind_speed_kmh=wind_kmh,
                    central_pressure_hpa=float(pressure_value) if pressure_value else None,
                ))
            except ValueError as exc:
                raise ManifestBuildError(f"IBTrACS row {row_number} has invalid coordinates or pressure") from exc
    if not result:
        raise ManifestBuildError("No IMD/New Delhi 3-minute wind observations were found in IBTrACS.")
    return result


def event_splits(event_ids: set[str], *, seed: int) -> dict[str, str]:
    """Assign each cyclone to exactly one deterministic split."""
    if len(event_ids) < 3:
        raise ManifestBuildError("At least three cyclone IDs are required for train/val/test event splits.")
    ordered = sorted(event_ids, key=lambda event_id: hashlib.sha256(f"{seed}:{event_id}".encode()).hexdigest())
    count = len(ordered)
    train_count = max(1, round(count * 0.7))
    val_count = max(1, round(count * 0.15))
    if train_count + val_count >= count:
        train_count, val_count = count - 2, 1
    return {
        **{event_id: "train" for event_id in ordered[:train_count]},
        **{event_id: "val" for event_id in ordered[train_count:train_count + val_count]},
        **{event_id: "test" for event_id in ordered[train_count + val_count:]},
    }


def build_manifest(*, ibtracs_path: Path, satellite_catalog_path: Path, output_dir: Path, tolerance_minutes: int, seed: int) -> dict[str, Any]:
    if tolerance_minutes < 0:
        raise ManifestBuildError("timestamp tolerance must be non-negative")
    best_track = load_newdelhi_best_track(ibtracs_path)
    by_event: dict[str, list[BestTrackPoint]] = {}
    for point in best_track:
        by_event.setdefault(point.cyclone_id, []).append(point)
    if not satellite_catalog_path.is_file():
        raise ManifestBuildError(f"Satellite catalog does not exist: {satellite_catalog_path}")

    matches: list[dict[str, Any]] = []
    with satellite_catalog_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"image_path", "source", "image_timestamp_utc", "cyclone_id"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ManifestBuildError(f"Satellite catalog is missing: {', '.join(sorted(missing))}")
        for row_number, row in enumerate(reader, start=2):
            cyclone_id = _value(row, "cyclone_id")
            observation_time = _timestamp(_value(row, "image_timestamp_utc"), context=f"Satellite row {row_number}")
            image_path = Path(_value(row, "image_path"))
            if not image_path.is_absolute():
                image_path = (satellite_catalog_path.parent / image_path).resolve()
            if not image_path.is_file():
                raise ManifestBuildError(f"Satellite row {row_number} references a missing image: {image_path}")
            candidates = by_event.get(cyclone_id, [])
            if not candidates:
                continue
            label = min(candidates, key=lambda point: abs((point.timestamp - observation_time).total_seconds()))
            delta_minutes = abs((label.timestamp - observation_time).total_seconds()) / 60
            if delta_minutes > tolerance_minutes:
                continue
            category = category_for_wind_kmh(label.wind_speed_kmh)
            assert category is not None
            matches.append({
                "image_path": str(image_path), "intensity_category": category, "source": _value(row, "source"),
                "image_timestamp_utc": observation_time.isoformat(), "label_timestamp_utc": label.timestamp.isoformat(),
                "latitude": label.latitude, "longitude": label.longitude, "cyclone_id": cyclone_id,
                "wind_speed_kmh": round(label.wind_speed_kmh, 3),
                "central_pressure_hpa": "" if label.central_pressure_hpa is None else label.central_pressure_hpa,
            })
    if not matches:
        raise ManifestBuildError("No satellite observations matched an IMD/New Delhi label within the configured tolerance.")
    splits = event_splits({match["cyclone_id"] for match in matches}, seed=seed)
    for match in matches:
        match["split"] = splits[match["cyclone_id"]]
    observed_categories = [category for category, _, _ in WIND_CATEGORIES if any(match["intensity_category"] == category for match in matches)]
    if len(observed_categories) < 2:
        raise ManifestBuildError("Matched data contains fewer than two genuine intensity categories.")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.csv"
    columns = ["image_path", "intensity_category", "source", "image_timestamp_utc", "label_timestamp_utc", "latitude", "longitude", "cyclone_id", "split", "wind_speed_kmh", "central_pressure_hpa"]
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader(); writer.writerows(matches)
    mapping = {"label_system": "IMD North Indian Ocean (3-minute sustained wind)", "source": "IBTrACS v04r01 New Delhi fields", "dataset_version": "assembled-local", "labels": observed_categories}
    (output_dir / "label_mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    event_ids_by_split = {split: sorted(event for event, assigned in splits.items() if assigned == split) for split in ("train", "val", "test")}
    (output_dir / "splits.json").write_text(json.dumps(event_ids_by_split, indent=2), encoding="utf-8")
    return {"manifest": str(manifest_path), "image_count": len(matches), "labels": observed_categories, "events_by_split": event_ids_by_split, "timestamp_tolerance_minutes": tolerance_minutes}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an event-split, timestamp-aligned intensity manifest")
    parser.add_argument("--ibtracs", type=Path, required=True)
    parser.add_argument("--satellite-catalog", type=Path, required=True, help="CSV of locally available satellite products and actual UTC acquisition timestamps")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timestamp-tolerance-minutes", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        print(json.dumps(build_manifest(ibtracs_path=args.ibtracs, satellite_catalog_path=args.satellite_catalog, output_dir=args.output_dir, tolerance_minutes=args.timestamp_tolerance_minutes, seed=args.seed), indent=2))
    except ManifestBuildError as exc:
        raise SystemExit(f"Intensity manifest build failed: {exc}") from exc


if __name__ == "__main__":
    main()
