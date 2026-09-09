"""Phase 4 safety tests: manifest integrity and honest model availability."""
from __future__ import annotations

import csv

import pytest
from httpx import ASGITransport, AsyncClient

from ai.detection.dataset import DatasetValidationError, load_manifest, validate_records
from ai.detection.service import DetectionService
from app.main import app


def _write_manifest(tmp_path, rows: list[dict[str, str]]):
    manifest = tmp_path / "manifest.csv"
    fieldnames = ["image_path", "label", "source", "timestamp", "latitude", "longitude", "cyclone_id", "split"]
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return manifest


def _row(image_path: str, label: str, event: str, split: str) -> dict[str, str]:
    return {
        "image_path": image_path, "label": label, "source": "research_dataset",
        "timestamp": "2020-05-18T18:00:00Z", "latitude": "14.5", "longitude": "86.3",
        "cyclone_id": event, "split": split,
    }


def test_manifest_reports_distribution_and_event_splits(tmp_path):
    rows = []
    for split, event in (("train", "AMPHAN"), ("val", "FANI"), ("test", "NISARGA")):
        for label in ("cyclone", "no_cyclone"):
            file_path = tmp_path / f"{event}-{label}.jpg"
            file_path.write_bytes(b"test fixture")
            rows.append(_row(file_path.name, label, event, split))
    report = validate_records(load_manifest(_write_manifest(tmp_path, rows)))
    assert report["class_distribution"] == {"cyclone": 3, "no_cyclone": 3}
    assert report["events_by_split"]["train"] == ["AMPHAN"]


def test_manifest_rejects_event_leakage_between_splits(tmp_path):
    rows = []
    for index, (label, event, split) in enumerate((
        ("cyclone", "AMPHAN", "train"), ("no_cyclone", "AMPHAN", "val"),
        ("cyclone", "FANI", "test"), ("no_cyclone", "NISARGA", "test"),
    )):
        file_path = tmp_path / f"image-{index}.jpg"
        file_path.write_bytes(b"test fixture")
        rows.append(_row(file_path.name, label, event, split))
    with pytest.raises(DatasetValidationError, match="data leakage"):
        validate_records(load_manifest(_write_manifest(tmp_path, rows)))


def test_detection_service_is_honest_when_no_checkpoint_exists(tmp_path):
    status = DetectionService(model_root=tmp_path).status()
    assert status.status == "MODEL_NOT_TRAINED"
    assert status.model_version is None


@pytest.mark.asyncio
async def test_detection_api_returns_model_not_trained_without_checkpoint(monkeypatch, tmp_path):
    service = DetectionService(model_root=tmp_path)
    monkeypatch.setattr("app.api.ai.get_detection_service", lambda: service)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        status_response = await client.get("/api/ai/detection/status")
        prediction_response = await client.post("/api/ai/detection?source=research_dataset")

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "MODEL_NOT_TRAINED"
    assert prediction_response.status_code == 503
    assert prediction_response.json()["status"] == "MODEL_NOT_TRAINED"
    assert prediction_response.json()["confidence"] is None

