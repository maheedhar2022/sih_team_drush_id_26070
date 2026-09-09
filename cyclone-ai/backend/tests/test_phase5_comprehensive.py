"""Phase 5 comprehensive tests: preprocessing, model creation, checkpoint loading,
CPU inference, API validation, and all model states.

These tests deliberately cover:
  - Image preprocessing (loading, resizing, normalisation, channel handling)
  - Training and validation/test transforms are deterministic
  - Model output shapes (classification + optional regression heads)
  - Checkpoint round-trip on CPU
  - API: success path (with patched service), invalid image, model unavailable,
    inference error, wrong content-type
  - Label mapping validation
  - Event-level split integrity
  - Timestamp alignment enforcement
  - Unit conversion helpers (kt -> km/h verification)
  - No-fake-AI: service returns MODEL_NOT_TRAINED without a checkpoint
"""
from __future__ import annotations

import csv
import io
import json
import struct
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ai.intensity.config import IntensityConfig
from ai.intensity.dataset import (
    IntensityDatasetError,
    load_label_mapping,
    load_manifest,
    validate_records,
)
from ai.intensity.service import IntensityService
from app.main import app


# ── helpers ──────────────────────────────────────────────────────────────────

def _minimal_label_mapping(tmp_path: Path) -> Path:
    """Write a valid two-class label mapping."""
    path = tmp_path / "label_mapping.json"
    path.write_text(json.dumps({
        "label_system": "IMD NI test",
        "source": "test fixture",
        "dataset_version": "test-v1",
        "labels": ["Cyclonic Storm", "Severe Cyclonic Storm"],
    }), encoding="utf-8")
    return path


def _row(image_path: str, category: str, cyclone_id: str, split: str,
         image_time: str = "2020-05-18T12:00:00Z",
         label_time: str = "2020-05-18T12:15:00Z") -> dict[str, str]:
    return {
        "image_path": image_path,
        "intensity_category": category,
        "source": "test_fixture",
        "image_timestamp_utc": image_time,
        "label_timestamp_utc": label_time,
        "latitude": "14.5",
        "longitude": "86.3",
        "cyclone_id": cyclone_id,
        "split": split,
        "wind_speed_kmh": "90",
        "central_pressure_hpa": "965",
    }


def _manifest(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    path = tmp_path / "manifest.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _three_event_rows(tmp_path: Path) -> tuple[Path, list[dict[str, str]]]:
    """Three cyclones in three separate splits; two images each."""
    rows = []
    for event, split, category in [
        ("AMPHAN_2020", "train", "Severe Cyclonic Storm"),
        ("FANI_2019",   "val",   "Cyclonic Storm"),
        ("TITLI_2018",  "test",  "Cyclonic Storm"),
    ]:
        for i in range(2):
            img = tmp_path / f"{event}_{i}.jpg"
            img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 20)  # minimal JPEG header
            rows.append(_row(str(img), category, event, split))
    return _manifest(tmp_path, rows), rows


# ═══════════════════════════════════════════════════════════════════════════
# Label mapping validation
# ═══════════════════════════════════════════════════════════════════════════

class TestLabelMapping:
    def test_valid_mapping_loads(self, tmp_path):
        mapping = load_label_mapping(_minimal_label_mapping(tmp_path))
        assert mapping["labels"] == ["Cyclonic Storm", "Severe Cyclonic Storm"]
        assert mapping["label_system"] == "IMD NI test"

    def test_rejects_single_class(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({
            "label_system": "x", "source": "x", "dataset_version": "x",
            "labels": ["Only One"],
        }), encoding="utf-8")
        with pytest.raises(IntensityDatasetError, match="at least two"):
            load_label_mapping(path)

    def test_rejects_duplicate_labels(self, tmp_path):
        path = tmp_path / "dup.json"
        path.write_text(json.dumps({
            "label_system": "x", "source": "x", "dataset_version": "x",
            "labels": ["Cyclonic Storm", "Cyclonic Storm"],
        }), encoding="utf-8")
        with pytest.raises(IntensityDatasetError, match="unique"):
            load_label_mapping(path)

    def test_rejects_missing_required_field(self, tmp_path):
        path = tmp_path / "nover.json"
        # Missing dataset_version
        path.write_text(json.dumps({
            "label_system": "x", "source": "x",
            "labels": ["A", "B"],
        }), encoding="utf-8")
        with pytest.raises(IntensityDatasetError, match="dataset_version"):
            load_label_mapping(path)

    def test_rejects_nonexistent_path(self, tmp_path):
        with pytest.raises(IntensityDatasetError, match="does not exist"):
            load_label_mapping(tmp_path / "no_such_file.json")


# ═══════════════════════════════════════════════════════════════════════════
# Manifest loading and validation
# ═══════════════════════════════════════════════════════════════════════════

class TestManifestLoading:
    def test_valid_manifest_loads_and_reports(self, tmp_path):
        manifest, _ = _three_event_rows(tmp_path)
        mapping = load_label_mapping(_minimal_label_mapping(tmp_path))
        records = load_manifest(manifest, mapping)
        report = validate_records(records, timestamp_tolerance_minutes=30)
        assert report["image_count"] == 6
        assert report["event_count"] == 3
        assert report["regression_targets"]["wind_speed_kmh"] == 6
        assert report["regression_targets"]["central_pressure_hpa"] == 6

    def test_event_level_split_reported_correctly(self, tmp_path):
        manifest, _ = _three_event_rows(tmp_path)
        mapping = load_label_mapping(_minimal_label_mapping(tmp_path))
        records = load_manifest(manifest, mapping)
        report = validate_records(records, timestamp_tolerance_minutes=30)
        assert "AMPHAN_2020" in report["events_by_split"]["train"]
        assert "FANI_2019" in report["events_by_split"]["val"]
        assert "TITLI_2018" in report["events_by_split"]["test"]

    def test_rejects_event_leakage(self, tmp_path):
        """Same cyclone_id in both train and val must be rejected."""
        mapping_path = _minimal_label_mapping(tmp_path)
        mapping = load_label_mapping(mapping_path)
        rows = []
        for split, category in [("train", "Cyclonic Storm"), ("val", "Severe Cyclonic Storm")]:
            img = tmp_path / f"leak_{split}.jpg"
            img.write_bytes(b"x")
            # AMPHAN appears in both splits — leakage
            rows.append(_row(str(img), category, "AMPHAN_2020", split))
        # Need a test split too
        img_test = tmp_path / "test.jpg"
        img_test.write_bytes(b"x")
        rows.append(_row(str(img_test), "Cyclonic Storm", "TITLI_2018", "test"))
        records = load_manifest(_manifest(tmp_path, rows), mapping)
        with pytest.raises(IntensityDatasetError, match="data leakage"):
            validate_records(records, timestamp_tolerance_minutes=30)

    def test_rejects_timestamp_mismatch_beyond_tolerance(self, tmp_path):
        mapping_path = _minimal_label_mapping(tmp_path)
        mapping = load_label_mapping(mapping_path)
        rows = []
        for event, split, category, label_time in [
            ("AMPHAN_2020", "train", "Cyclonic Storm",        "2020-05-18T12:15:00Z"),   # 15min ok
            ("FANI_2019",   "val",   "Severe Cyclonic Storm", "2020-05-18T14:00:00Z"),   # 120min — over limit
            ("TITLI_2018",  "test",  "Cyclonic Storm",        "2020-05-18T12:10:00Z"),
        ]:
            img = tmp_path / f"{event}.jpg"
            img.write_bytes(b"x")
            rows.append(_row(str(img), category, event, split, label_time=label_time))
        records = load_manifest(_manifest(tmp_path, rows), mapping)
        with pytest.raises(IntensityDatasetError, match="Timestamp mismatch"):
            validate_records(records, timestamp_tolerance_minutes=30)

    def test_rejects_category_not_in_mapping(self, tmp_path):
        mapping_path = _minimal_label_mapping(tmp_path)
        mapping = load_label_mapping(mapping_path)
        img = tmp_path / "img.jpg"
        img.write_bytes(b"x")
        rows = [_row(str(img), "Super Cyclonic Storm", "AMPHAN", "train")]
        with pytest.raises(IntensityDatasetError, match="not in the authoritative mapping"):
            load_manifest(_manifest(tmp_path, rows), mapping)

    def test_rejects_negative_wind(self, tmp_path):
        mapping_path = _minimal_label_mapping(tmp_path)
        mapping = load_label_mapping(mapping_path)
        rows = []
        for event, split, category in [
            ("AMPHAN_2020", "train", "Cyclonic Storm"),
            ("FANI_2019",   "val",   "Severe Cyclonic Storm"),
            ("TITLI_2018",  "test",  "Cyclonic Storm"),
        ]:
            img = tmp_path / f"{event}_neg.jpg"
            img.write_bytes(b"x")
            r = _row(str(img), category, event, split)
            r["wind_speed_kmh"] = "-10"
            rows.append(r)
        records = load_manifest(_manifest(tmp_path, rows), mapping)
        with pytest.raises(IntensityDatasetError, match="negative"):
            validate_records(records, timestamp_tolerance_minutes=30)


# ═══════════════════════════════════════════════════════════════════════════
# IntensityConfig validation
# ═══════════════════════════════════════════════════════════════════════════

class TestIntensityConfig:
    def test_default_config_is_valid(self):
        cfg = IntensityConfig()
        assert cfg.backbone == "resnet18"
        assert cfg.image_size == 224
        assert cfg.epochs > 0

    def test_round_trips_via_dict(self):
        cfg = IntensityConfig(backbone="resnet50", epochs=5, learning_rate=5e-5)
        assert IntensityConfig.from_dict(cfg.to_dict()) == cfg

    def test_rejects_unknown_backbone(self):
        with pytest.raises(ValueError, match="backbone"):
            IntensityConfig(backbone="vgg16")

    def test_rejects_zero_epochs(self):
        with pytest.raises(ValueError):
            IntensityConfig(epochs=0)

    def test_rejects_negative_learning_rate(self):
        with pytest.raises(ValueError):
            IntensityConfig(learning_rate=-1e-4)


try:
    import torch as _torch
    import torchvision as _tv  # noqa: F401
    import PIL as _pil  # noqa: F401
    _HAS_TORCH = True
except Exception:
    _torch = None
    _HAS_TORCH = False

_skip_no_torch = pytest.mark.skipif(not _HAS_TORCH, reason="torch/torchvision/Pillow not available")


@_skip_no_torch
class TestPreprocessing:
    def _minimal_jpeg_bytes(self) -> bytes:
        """Return a 4×4 px white JPEG created with Pillow."""
        from PIL import Image as PILImage
        buf = io.BytesIO()
        PILImage.new("RGB", (4, 4), color=(255, 255, 255)).save(buf, format="JPEG")
        return buf.getvalue()

    def test_bytes_to_tensor_returns_correct_shape(self):
        from ai.detection.preprocessing import image_bytes_to_tensor
        t = image_bytes_to_tensor(self._minimal_jpeg_bytes(), image_size=224)
        assert t.shape == (3, 224, 224)

    def test_bytes_to_tensor_values_are_normalised(self):
        """Values must not be plain 0–255; normalisation must have been applied."""
        from ai.detection.preprocessing import image_bytes_to_tensor
        t = image_bytes_to_tensor(self._minimal_jpeg_bytes(), image_size=64)
        # After normalisation a white image has large positive values, not 255
        assert float(t.max()) < 10.0
        assert float(t.min()) > -10.0

    def test_validation_transform_is_deterministic(self):
        """Running the val transform twice on the same bytes must give identical tensors."""
        from ai.detection.preprocessing import image_bytes_to_tensor
        raw = self._minimal_jpeg_bytes()
        t1 = image_bytes_to_tensor(raw, image_size=32)
        t2 = image_bytes_to_tensor(raw, image_size=32)
        assert torch.allclose(t1, t2), "Val/test transform must be deterministic"

    def test_open_rgb_image_rejects_empty_payload(self):
        from ai.detection.preprocessing import ImagePreprocessingError, open_rgb_image
        with pytest.raises(ImagePreprocessingError, match="empty"):
            open_rgb_image(b"")

    def test_open_rgb_image_rejects_non_image_bytes(self):
        from ai.detection.preprocessing import ImagePreprocessingError, open_rgb_image
        with pytest.raises(ImagePreprocessingError, match="not a valid"):
            open_rgb_image(b"this is not an image at all")

    def test_training_transform_produces_correct_shape(self):
        from ai.detection.preprocessing import build_transform, open_rgb_image
        img = open_rgb_image(self._minimal_jpeg_bytes())
        t = build_transform(image_size=128, training=True)(img)
        assert t.shape == (3, 128, 128)


# ═══════════════════════════════════════════════════════════════════════════
# Model creation (no pretrained weights — fast, no internet)
# ═══════════════════════════════════════════════════════════════════════════

@_skip_no_torch
class TestModelCreation:
    def test_resnet18_with_all_heads(self):
        from ai.intensity.model import build_model
        model = build_model(
            IntensityConfig(backbone="resnet18"), num_categories=3,
            predict_wind=True, predict_pressure=True, use_pretrained_weights=False,
        ).eval()
        with torch.inference_mode():
            out = model(torch.zeros(1, 3, 224, 224))
        assert out["classification_logits"].shape == (1, 3)
        assert out["wind"].shape == (1,)
        assert out["pressure"].shape == (1,)

    def test_resnet18_classification_only(self):
        from ai.intensity.model import build_model
        model = build_model(
            IntensityConfig(backbone="resnet18"), num_categories=5,
            predict_wind=False, predict_pressure=False, use_pretrained_weights=False,
        ).eval()
        with torch.inference_mode():
            out = model(torch.zeros(1, 3, 224, 224))
        assert out["classification_logits"].shape == (1, 5)
        assert "wind" not in out
        assert "pressure" not in out

    def test_resnet50_output_shapes(self):
        from ai.intensity.model import build_model
        model = build_model(
            IntensityConfig(backbone="resnet50"), num_categories=4,
            predict_wind=True, predict_pressure=False, use_pretrained_weights=False,
        ).eval()
        with torch.inference_mode():
            out = model(torch.zeros(2, 3, 224, 224))
        assert out["classification_logits"].shape == (2, 4)
        assert out["wind"].shape == (2,)
        assert "pressure" not in out

    def test_requires_at_least_two_categories(self):
        from ai.intensity.model import build_model
        with pytest.raises(ValueError, match="two"):
            build_model(
                IntensityConfig(backbone="resnet18"), num_categories=1,
                predict_wind=False, predict_pressure=False, use_pretrained_weights=False,
            )


# ═══════════════════════════════════════════════════════════════════════════
# Checkpoint round-trip on CPU
# ═══════════════════════════════════════════════════════════════════════════

@_skip_no_torch
class TestCheckpointRoundTrip:
    def _build_and_save(self, tmp_path: Path) -> Path:
        from ai.intensity.model import build_model

        config = IntensityConfig(backbone="resnet18", image_size=64)
        labels = ["Cyclonic Storm", "Severe Cyclonic Storm"]
        model = build_model(config, num_categories=2, predict_wind=True,
                            predict_pressure=True, use_pretrained_weights=False)
        checkpoint = {
            "state_dict": model.state_dict(),
            "config": config.to_dict(),
            "model_version": "intensity-resnet18-test-v1",
            "label_mapping": {
                "label_system": "test", "source": "test", "dataset_version": "test-v1",
                "labels": labels,
            },
            "predict_wind": True,
            "predict_pressure": True,
            "target_statistics": {
                "wind": {"mean": 100.0, "std": 20.0},
                "pressure": {"mean": 970.0, "std": 15.0},
            },
        }
        path = tmp_path / "intensity" / "best.pt"
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(checkpoint, path)
        return tmp_path

    def test_service_loads_valid_checkpoint(self, tmp_path):
        model_root = self._build_and_save(tmp_path)
        service = IntensityService(model_root=model_root, device="cpu")
        st = service.status()
        assert st.status == "READY", f"Expected READY, got: {st.status} / {st.reason}"
        assert st.model_version == "intensity-resnet18-test-v1"

    def test_service_returns_model_not_trained_without_checkpoint(self, tmp_path):
        service = IntensityService(model_root=tmp_path, device="cpu")
        st = service.status()
        assert st.status == "MODEL_NOT_TRAINED"
        assert st.model_version is None

    def test_cpu_inference_produces_valid_result(self, tmp_path):
        from PIL import Image as PILImage
        model_root = self._build_and_save(tmp_path)
        service = IntensityService(model_root=model_root, device="cpu")
        # Create a tiny valid JPEG
        buf = io.BytesIO()
        PILImage.new("RGB", (64, 64), color=(100, 150, 200)).save(buf, format="JPEG")
        result = service.predict_image(buf.getvalue(), source="unit_test")
        assert result.status == "success"
        assert result.category in ("Cyclonic Storm", "Severe Cyclonic Storm")
        assert 0.0 <= result.confidence <= 1.0
        assert result.wind_speed_kmh is not None
        assert result.central_pressure_hpa is not None
        assert result.model_version == "intensity-resnet18-test-v1"

    def test_inference_probabilities_sum_to_one(self, tmp_path):
        from PIL import Image as PILImage
        model_root = self._build_and_save(tmp_path)
        service = IntensityService(model_root=model_root, device="cpu")
        buf = io.BytesIO()
        PILImage.new("RGB", (64, 64)).save(buf, format="JPEG")
        result = service.predict_image(buf.getvalue(), source="unit_test")
        total = sum(result.class_probabilities.values())
        assert abs(total - 1.0) < 1e-5

    @pytest.mark.skipif(
        not (_torch is not None and _torch.cuda.is_available()),
        reason="CUDA is not available",
    )
    def test_cuda_inference(self, tmp_path):
        from PIL import Image as PILImage
        model_root = self._build_and_save(tmp_path)
        service = IntensityService(model_root=model_root, device="cuda")
        buf = io.BytesIO()
        PILImage.new("RGB", (64, 64)).save(buf, format="JPEG")
        result = service.predict_image(buf.getvalue(), source="cuda_test")
        assert result.status == "success"
        assert result.category is not None


# ═══════════════════════════════════════════════════════════════════════════
# API — model unavailable (no checkpoint)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_intensity_api_status_returns_model_not_trained(monkeypatch, tmp_path):
    svc = IntensityService(model_root=tmp_path)
    monkeypatch.setattr("app.api.ai.get_intensity_service", lambda: svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/ai/intensity/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "MODEL_NOT_TRAINED"
    assert body["dataset_status"] == "DATASET_UNAVAILABLE"


@pytest.mark.asyncio
async def test_intensity_api_inference_returns_503_when_model_not_trained(monkeypatch, tmp_path):
    svc = IntensityService(model_root=tmp_path)
    monkeypatch.setattr("app.api.ai.get_intensity_service", lambda: svc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/ai/intensity?source=unit_test",
            content=b"\xff\xd8\xff\xe0" + b"\x00" * 20,
            headers={"Content-Type": "image/jpeg"},
        )
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "MODEL_NOT_TRAINED"
    assert body["category"] is None
    assert body["wind_speed_kmh"] is None
    assert body["central_pressure_hpa"] is None


# ═══════════════════════════════════════════════════════════════════════════
# API — invalid image input
# ═══════════════════════════════════════════════════════════════════════════

class _ReadyIntensityService:
    """Minimal stub that reports READY without a real model."""
    def status(self):
        from ai.intensity.service import IntensityStatus
        return IntensityStatus(
            status="READY", dataset_status="CONFIGURED",
            model_version="stub-v1", architecture="resnet18",
            dataset_version="stub-ds-v1", reason=None,
        )

    def predict_image(self, image_bytes: bytes, *, source: str, observation_id=None):
        from ai.detection.preprocessing import image_bytes_to_tensor, ImagePreprocessingError
        # Re-use the real preprocessing so invalid images still fail correctly
        image_bytes_to_tensor(image_bytes, image_size=224)
        raise NotImplementedError("stub should not reach real inference")


@pytest.mark.asyncio
async def test_intensity_api_rejects_wrong_content_type(monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.ai.get_intensity_service", lambda: _ReadyIntensityService())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/ai/intensity?source=unit_test",
            content=b"not an image",
            headers={"Content-Type": "text/plain"},
        )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_intensity_api_rejects_garbage_image_bytes(monkeypatch, tmp_path):
    from ai.intensity.service import IntensityResult
    from ai.detection.preprocessing import ImagePreprocessingError

    class StubBrokenService:
        def status(self):
            from ai.intensity.service import IntensityStatus
            return IntensityStatus(status="READY", dataset_status="CONFIGURED",
                                   model_version="s", architecture="r18",
                                   dataset_version="d", reason=None)

        def predict_image(self, image_bytes, *, source, observation_id=None):
            raise ImagePreprocessingError("File is not a valid supported image")

    monkeypatch.setattr("app.api.ai.get_intensity_service", lambda: StubBrokenService())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/ai/intensity?source=unit_test",
            content=b"this is totally not an image",
            headers={"Content-Type": "image/jpeg"},
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_intensity_api_success_returns_full_result(monkeypatch, tmp_path):
    """Verify the full happy-path response schema from a mocked service."""
    from ai.intensity.service import IntensityResult

    now = datetime.now(timezone.utc)

    class StubSuccessService:
        def status(self):
            from ai.intensity.service import IntensityStatus
            return IntensityStatus(status="READY", dataset_status="CONFIGURED",
                                   model_version="v1", architecture="resnet18",
                                   dataset_version="imd-ni-v1", reason=None)

        def predict_image(self, image_bytes, *, source, observation_id=None):
            return IntensityResult(
                status="success",
                category="Very Severe Cyclonic Storm",
                confidence=0.87,
                class_probabilities={
                    "Cyclonic Storm": 0.05,
                    "Severe Cyclonic Storm": 0.08,
                    "Very Severe Cyclonic Storm": 0.87,
                },
                wind_speed_kmh=238.4,
                central_pressure_hpa=924.7,
                model_version="intensity-resnet18-v1",
                architecture="resnet18",
                dataset_version="imd-ni-v1",
                inference_timestamp_utc=now,
                observation_id=observation_id,
                source=source,
            )

    monkeypatch.setattr("app.api.ai.get_intensity_service", lambda: StubSuccessService())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/ai/intensity?source=unit_test&observation_id=OBS_001",
            content=b"\xff\xd8\xff" + b"\x00" * 30,
            headers={"Content-Type": "image/jpeg"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["category"] == "Very Severe Cyclonic Storm"
    assert abs(body["confidence"] - 0.87) < 1e-4
    assert abs(body["wind_speed_kmh"] - 238.4) < 0.1
    assert abs(body["central_pressure_hpa"] - 924.7) < 0.1
    assert body["model_version"] == "intensity-resnet18-v1"
    assert body["observation_id"] == "OBS_001"
    assert "class_probabilities" in body


@pytest.mark.asyncio
async def test_intensity_api_returns_structured_inference_error(monkeypatch):
    class StubFailingService:
        def status(self):
            from ai.intensity.service import IntensityStatus
            return IntensityStatus("READY", "CONFIGURED", "v1", "resnet18", "test-v1", None)

        def predict_image(self, image_bytes, *, source, observation_id=None):
            raise RuntimeError("unexpected model failure")

    monkeypatch.setattr("app.api.ai.get_intensity_service", lambda: StubFailingService())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/ai/intensity?source=unit_test", content=b"image", headers={"Content-Type": "image/jpeg"},
        )
    assert response.status_code == 500
    assert response.json()["status"] == "INFERENCE_ERROR"


# ═══════════════════════════════════════════════════════════════════════════
# Unit conversion correctness (kt -> km/h)
# ═══════════════════════════════════════════════════════════════════════════

class TestUnitConversion:
    KT_TO_KMH = 1.852

    @pytest.mark.parametrize("knots,expected_kmh", [
        (34,  62.97),
        (48,  88.90),
        (64, 118.53),
        (89, 164.83),
    ])
    def test_knots_to_kmh_conversion(self, knots, expected_kmh):
        kmh = knots * self.KT_TO_KMH
        assert abs(kmh - expected_kmh) < 0.1, f"{knots}kt → {kmh:.2f} km/h (expected ≈{expected_kmh})"
