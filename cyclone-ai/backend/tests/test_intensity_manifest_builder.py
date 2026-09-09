"""Tests for the provenance-safe Phase 5 manifest assembly command."""
from __future__ import annotations

import csv
import json

import pytest

from ai.training.build_intensity_manifest import ManifestBuildError, build_manifest, load_newdelhi_best_track


def _write_ibtracs(path, rows):
    fields = ["SID", "ISO_TIME", "LAT", "LON", "NEWDELHI_WIND", "NEWDELHI_PRES", "USA_WIND"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def test_builder_creates_timestamp_aligned_event_splits_and_mapping(tmp_path):
    ibtracs = tmp_path / "ibtracs.csv"
    rows, catalog_rows = [], []
    for index, (sid, wind) in enumerate((("A", "20"), ("B", "40"), ("C", "65"))):
        timestamp = f"2020-05-{18 + index:02d}T12:00:00Z"
        rows.append({"SID": sid, "ISO_TIME": timestamp.replace("T", " ").replace("Z", ""), "LAT": "14.5", "LON": "86.3", "NEWDELHI_WIND": wind, "NEWDELHI_PRES": "970", "USA_WIND": ""})
        image = tmp_path / f"{sid}.png"; image.write_bytes(b"real-image-placeholder")
        catalog_rows.append({"image_path": image.name, "source": "validated_satellite_product", "image_timestamp_utc": timestamp, "cyclone_id": sid})
    _write_ibtracs(ibtracs, rows)
    catalog = tmp_path / "catalog.csv"
    with catalog.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(catalog_rows[0])); writer.writeheader(); writer.writerows(catalog_rows)

    report = build_manifest(ibtracs_path=ibtracs, satellite_catalog_path=catalog, output_dir=tmp_path / "out", tolerance_minutes=30, seed=42)

    assert report["image_count"] == 3
    assert report["labels"] == ["Depression", "Cyclonic Storm", "Very Severe Cyclonic Storm"]
    assert all(len(events) == 1 for events in report["events_by_split"].values())
    mapping = json.loads((tmp_path / "out" / "label_mapping.json").read_text(encoding="utf-8"))
    assert mapping["labels"] == report["labels"]


def test_builder_refuses_usa_one_minute_wind_as_imd_label(tmp_path):
    ibtracs = tmp_path / "ibtracs.csv"
    _write_ibtracs(ibtracs, [{"SID": "A", "ISO_TIME": "2020-05-18 12:00:00", "LAT": "14", "LON": "86", "NEWDELHI_WIND": "", "NEWDELHI_PRES": "", "USA_WIND": "64"}])

    with pytest.raises(ManifestBuildError, match="No IMD/New Delhi"):
        load_newdelhi_best_track(ibtracs)
