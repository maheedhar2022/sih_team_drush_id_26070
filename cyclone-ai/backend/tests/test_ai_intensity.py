"""Phase 5 dataset, availability, and API safety tests."""
from __future__ import annotations

import csv
import json

import pytest
from httpx import ASGITransport, AsyncClient

from ai.intensity.dataset import IntensityDatasetError, load_label_mapping, load_manifest, validate_records
from ai.intensity.service import IntensityService
from app.main import app


def _mapping(tmp_path):
    path = tmp_path / "label_mapping.json"
    path.write_text(json.dumps({
        "label_system": "fixture scale", "source": "fixture dataset", "dataset_version": "fixture-v1",
        "labels": ["Depression", "Cyclonic Storm"],
    }), encoding="utf-8")
    return path


def _row(image_path: str, category: str, event: str, split: str, *, image_time: str = "2020-05-18T18:00:00Z", label_time: str = "2020-05-18T18:20:00Z"):
    return {
        "image_path": image_path, "intensity_category": category, "source": "research_dataset",
        "image_timestamp_utc": image_time, "label_timestamp_utc": label_time,
        "latitude": "14.5", "longitude": "86.3", "cyclone_id": event, "split": split,
        "wind_speed_kmh": "80", "central_pressure_hpa": "980",
    }


def _manifest(tmp_path, rows):
    path = tmp_path / "manifest.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    return path


def test_intensity_manifest_preserves_event_split_and_targets(tmp_path):
    rows = []
    for index, (event, split) in enumerate((("AMPHAN", "train"), ("FANI", "val"), ("NISARGA", "test"))):
        for category in ("Depression", "Cyclonic Storm"):
            image = tmp_path / f"{index}-{category}.jpg"; image.write_bytes(b"fixture")
            rows.append(_row(image.name, category, event, split))
    records = load_manifest(_manifest(tmp_path, rows), load_label_mapping(_mapping(tmp_path)))
    report = validate_records(records, timestamp_tolerance_minutes=30)
    assert report["events_by_split"]["test"] == ["NISARGA"]
    assert report["regression_targets"] == {"wind_speed_kmh": 6, "central_pressure_hpa": 6}


def test_intensity_manifest_rejects_timestamp_mismatch(tmp_path):
    rows = []
    for index, (event, split, category) in enumerate((("AMPHAN", "train", "Depression"), ("FANI", "val", "Cyclonic Storm"), ("NISARGA", "test", "Depression"))):
        image = tmp_path / f"{index}.jpg"; image.write_bytes(b"fixture")
        rows.append(_row(image.name, category, event, split, label_time="2020-05-18T20:00:00Z" if event == "AMPHAN" else "2020-05-18T18:20:00Z"))
    with pytest.raises(IntensityDatasetError, match="Timestamp mismatch"):
        validate_records(load_manifest(_manifest(tmp_path, rows), load_label_mapping(_mapping(tmp_path))), timestamp_tolerance_minutes=30)


def test_intensity_manifest_rejects_event_leakage(tmp_path):
    rows = []
    for index, (event, split, category) in enumerate((("AMPHAN", "train", "Depression"), ("AMPHAN", "val", "Cyclonic Storm"), ("NISARGA", "test", "Depression"))):
        image = tmp_path / f"{index}.jpg"; image.write_bytes(b"fixture")
        rows.append(_row(image.name, category, event, split))
    with pytest.raises(IntensityDatasetError, match="data leakage"):
        validate_records(load_manifest(_manifest(tmp_path, rows), load_label_mapping(_mapping(tmp_path))), timestamp_tolerance_minutes=30)


@pytest.mark.asyncio
async def test_intensity_api_reports_dataset_unavailable_without_checkpoint(monkeypatch, tmp_path):
    service = IntensityService(model_root=tmp_path)
    monkeypatch.setattr("app.api.ai.get_intensity_service", lambda: service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status = await client.get("/api/ai/intensity/status")
        inference = await client.post("/api/ai/intensity?source=research_dataset")
    assert status.status_code == 200
    assert status.json()["status"] == "MODEL_NOT_TRAINED"
    assert status.json()["dataset_status"] == "DATASET_UNAVAILABLE"
    assert inference.status_code == 503
    assert inference.json()["category"] is None
    assert inference.json()["wind_speed_kmh"] is None

