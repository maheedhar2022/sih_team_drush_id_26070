"""Validated intensity manifests with event and timestamp safeguards."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = {
    "image_path", "intensity_category", "source", "image_timestamp_utc",
    "label_timestamp_utc", "latitude", "longitude", "cyclone_id", "split",
}
OPTIONAL_TARGET_COLUMNS = {"wind_speed_kmh", "central_pressure_hpa"}
VALID_SPLITS = {"train", "val", "test"}


class IntensityDatasetError(ValueError):
    """The supplied Phase 5 dataset cannot safely support training."""


@dataclass(frozen=True)
class IntensityRecord:
    image_path: Path
    intensity_category: str
    source: str
    image_timestamp_utc: datetime
    label_timestamp_utc: datetime
    latitude: float
    longitude: float
    cyclone_id: str
    split: str
    wind_speed_kmh: float | None
    central_pressure_hpa: float | None


def load_label_mapping(path: str | Path) -> dict[str, Any]:
    mapping_path = Path(path)
    if not mapping_path.is_file():
        raise IntensityDatasetError(f"Label mapping does not exist: {mapping_path}")
    try:
        payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IntensityDatasetError("Label mapping must be valid JSON") from exc
    labels = payload.get("labels") if isinstance(payload, dict) else None
    if not isinstance(labels, list) or len(labels) < 2 or not all(isinstance(label, str) and label.strip() for label in labels):
        raise IntensityDatasetError("Label mapping must contain at least two non-empty ordered labels")
    if len(set(labels)) != len(labels):
        raise IntensityDatasetError("Label mapping labels must be unique")
    for key in ("label_system", "source", "dataset_version"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise IntensityDatasetError(f"Label mapping requires a non-empty {key}")
    return payload


def _parse_timestamp(value: str, field: str, row_number: int) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntensityDatasetError(f"Row {row_number}: {field} must be ISO-8601 UTC") from exc
    if parsed.tzinfo is None:
        raise IntensityDatasetError(f"Row {row_number}: {field} must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _optional_float(value: str, field: str, row_number: int) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise IntensityDatasetError(f"Row {row_number}: {field} must be numeric when supplied") from exc


def load_manifest(manifest_path: str | Path, label_mapping: dict[str, Any]) -> list[IntensityRecord]:
    path = Path(manifest_path)
    if not path.is_file():
        raise IntensityDatasetError(f"Manifest does not exist: {path}")
    allowed_labels = set(label_mapping["labels"])
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - headers
        if missing:
            raise IntensityDatasetError(f"Manifest is missing required columns: {', '.join(sorted(missing))}")
        records: list[IntensityRecord] = []
        for row_number, row in enumerate(reader, start=2):
            values = {key: (row.get(key) or "").strip() for key in REQUIRED_COLUMNS | OPTIONAL_TARGET_COLUMNS}
            if not values["image_path"] or not values["source"] or not values["cyclone_id"]:
                raise IntensityDatasetError(f"Row {row_number}: image_path, source, and cyclone_id are required")
            if values["split"] not in VALID_SPLITS:
                raise IntensityDatasetError(f"Row {row_number}: split must be train, val, or test")
            if values["intensity_category"] not in allowed_labels:
                raise IntensityDatasetError(f"Row {row_number}: intensity_category is not in the authoritative mapping")
            try:
                latitude, longitude = float(values["latitude"]), float(values["longitude"])
            except ValueError as exc:
                raise IntensityDatasetError(f"Row {row_number}: latitude and longitude must be numeric") from exc
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise IntensityDatasetError(f"Row {row_number}: latitude or longitude is out of range")
            image_path = Path(values["image_path"])
            if not image_path.is_absolute():
                image_path = path.parent / image_path
            records.append(IntensityRecord(
                image_path=image_path.resolve(), intensity_category=values["intensity_category"], source=values["source"],
                image_timestamp_utc=_parse_timestamp(values["image_timestamp_utc"], "image_timestamp_utc", row_number),
                label_timestamp_utc=_parse_timestamp(values["label_timestamp_utc"], "label_timestamp_utc", row_number),
                latitude=latitude, longitude=longitude, cyclone_id=values["cyclone_id"], split=values["split"],
                wind_speed_kmh=_optional_float(values["wind_speed_kmh"], "wind_speed_kmh", row_number),
                central_pressure_hpa=_optional_float(values["central_pressure_hpa"], "central_pressure_hpa", row_number),
            ))
    if not records:
        raise IntensityDatasetError("Manifest does not contain image records")
    return records


def validate_records(records: list[IntensityRecord], *, timestamp_tolerance_minutes: int, check_images: bool = True) -> dict[str, Any]:
    """Validate images, labels, event splits, and image-to-label temporal alignment."""
    events: dict[str, set[str]] = defaultdict(set)
    missing_images: list[str] = []
    category_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    wind_count = pressure_count = 0
    for record in records:
        events[record.cyclone_id].add(record.split)
        category_counts[record.intensity_category] += 1
        split_counts[record.split] += 1
        if check_images and not record.image_path.is_file():
            missing_images.append(str(record.image_path))
        alignment_minutes = abs((record.image_timestamp_utc - record.label_timestamp_utc).total_seconds()) / 60
        if alignment_minutes > timestamp_tolerance_minutes:
            raise IntensityDatasetError(
                f"Timestamp mismatch for {record.cyclone_id}: {alignment_minutes:.1f} minutes exceeds "
                f"the {timestamp_tolerance_minutes}-minute tolerance"
            )
        if record.wind_speed_kmh is not None:
            if record.wind_speed_kmh < 0:
                raise IntensityDatasetError("Wind speed cannot be negative")
            wind_count += 1
        if record.central_pressure_hpa is not None:
            if record.central_pressure_hpa <= 0:
                raise IntensityDatasetError("Central pressure must be positive")
            pressure_count += 1
    leaked_events = sorted(event for event, splits in events.items() if len(splits) > 1)
    if leaked_events:
        raise IntensityDatasetError(
            "Event-level data leakage: the same cyclone/event is in multiple splits "
            f"({', '.join(leaked_events[:5])})"
        )
    if missing_images:
        raise IntensityDatasetError(f"Manifest references missing image files: {', '.join(missing_images[:3])}")
    if len(category_counts) < 2:
        raise IntensityDatasetError("At least two mapped intensity categories are required")
    if not all(split_counts.get(split) for split in VALID_SPLITS):
        raise IntensityDatasetError("Train, val, and test splits must each contain images")
    return {
        "image_count": len(records), "event_count": len(events),
        "category_distribution": dict(sorted(category_counts.items())),
        "split_distribution": dict(sorted(split_counts.items())),
        "regression_targets": {"wind_speed_kmh": wind_count, "central_pressure_hpa": pressure_count},
        "events_by_split": {split: sorted(event for event, splits in events.items() if split in splits) for split in sorted(VALID_SPLITS)},
        "timestamp_tolerance_minutes": timestamp_tolerance_minutes,
    }


def records_for_split(records: list[IntensityRecord], split: str) -> list[IntensityRecord]:
    return [record for record in records if record.split == split]

