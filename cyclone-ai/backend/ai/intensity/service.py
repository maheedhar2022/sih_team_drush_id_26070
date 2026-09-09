"""Lazy, in-memory inference service for a trained Phase 5 checkpoint."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from ai.detection.preprocessing import image_bytes_to_tensor
from ai.detection.service import ModelDependencyError, ModelNotTrainedError

from .config import IntensityConfig, default_model_path
from .model import build_model


@dataclass(frozen=True)
class IntensityStatus:
    status: str
    dataset_status: str
    model_version: str | None
    architecture: str | None
    dataset_version: str | None
    reason: str | None


@dataclass(frozen=True)
class IntensityResult:
    status: str
    category: str
    confidence: float
    class_probabilities: dict[str, float]
    wind_speed_kmh: float | None
    central_pressure_hpa: float | None
    model_version: str
    architecture: str
    dataset_version: str
    inference_timestamp_utc: datetime
    observation_id: str | None
    source: str


class IntensityService:
    def __init__(self, model_root: str | Path | None = None, device: str | None = None) -> None:
        settings = get_settings()
        self.model_root = Path(model_root or settings.ai_model_dir).expanduser()
        self.requested_device = device or settings.ai_device
        self._model: Any | None = None
        self._config: IntensityConfig | None = None
        self._metadata: dict[str, Any] = {}
        self._device: Any | None = None
        self._loaded_mtime_ns: int | None = None
        self._is_loading = False

    @property
    def checkpoint_path(self) -> Path:
        return default_model_path(self.model_root)

    def status(self) -> IntensityStatus:
        if not self.checkpoint_path.is_file():
            return IntensityStatus(
                status="MODEL_NOT_TRAINED", dataset_status="DATASET_UNAVAILABLE", model_version=None,
                architecture=None, dataset_version=None,
                reason="No intensity-labelled, event-split satellite dataset or trained intensity checkpoint is available.",
            )
        try:
            import torch  # noqa: F401
            import torchvision  # noqa: F401
            import PIL  # noqa: F401
        except Exception:
            return IntensityStatus(
                status="DEPENDENCY_UNAVAILABLE", dataset_status="UNKNOWN", model_version=None,
                architecture=None, dataset_version=None,
                reason="The intensity checkpoint exists but PyTorch, Torchvision, or Pillow is not installed.",
            )
        if self._is_loading:
            return IntensityStatus(
                status="MODEL_LOADING", dataset_status="CONFIGURED", model_version=None,
                architecture=None, dataset_version=None, reason="Intensity checkpoint is loading.",
            )
        try:
            self._load()
        except (ModelNotTrainedError, ModelDependencyError) as exc:
            return IntensityStatus(
                status="INFERENCE_ERROR", dataset_status="CONFIGURED", model_version=None,
                architecture=None, dataset_version=None, reason=str(exc),
            )
        except Exception:
            return IntensityStatus(
                status="INFERENCE_ERROR", dataset_status="CONFIGURED", model_version=None,
                architecture=None, dataset_version=None, reason="Intensity checkpoint could not be loaded.",
            )
        return IntensityStatus(
            status="READY", dataset_status="CONFIGURED", model_version=self._metadata.get("model_version"),
            architecture=self._config.backbone if self._config else None,
            dataset_version=self._config.dataset_version if self._config else None, reason=None,
        )

    def _select_device(self) -> Any:
        try:
            import torch
        except ImportError as exc:
            raise ModelDependencyError("PyTorch is not installed.") from exc
        if self.requested_device == "cuda" and not torch.cuda.is_available():
            raise ModelDependencyError("AI_DEVICE=cuda was requested but CUDA is unavailable.")
        return torch.device("cpu" if self.requested_device == "cpu" else "cuda" if torch.cuda.is_available() else "cpu")

    def _load(self) -> None:
        path = self.checkpoint_path
        if not path.is_file():
            raise ModelNotTrainedError("No trained intensity checkpoint is available.")
        mtime_ns = path.stat().st_mtime_ns
        if self._model is not None and self._loaded_mtime_ns == mtime_ns:
            return
        try:
            import torch
        except ImportError as exc:
            raise ModelDependencyError("PyTorch is not installed.") from exc
        self._is_loading = True
        try:
            device = self._select_device()
            try:
                checkpoint = torch.load(path, map_location=device, weights_only=False)
            except TypeError:
                checkpoint = torch.load(path, map_location=device)
            required = {"state_dict", "config", "model_version", "label_mapping", "predict_wind", "predict_pressure", "target_statistics"}
            if not isinstance(checkpoint, dict) or not required.issubset(checkpoint):
                raise ModelNotTrainedError("Intensity checkpoint is incomplete or incompatible.")
            mapping = checkpoint["label_mapping"]
            labels = mapping.get("labels") if isinstance(mapping, dict) else None
            if not isinstance(labels, list) or len(labels) < 2:
                raise ModelNotTrainedError("Intensity checkpoint has no valid label mapping.")
            config = IntensityConfig.from_dict(checkpoint["config"])
            model = build_model(
                config, num_categories=len(labels), predict_wind=bool(checkpoint["predict_wind"]),
                predict_pressure=bool(checkpoint["predict_pressure"]), use_pretrained_weights=False,
            )
            model.load_state_dict(checkpoint["state_dict"])
            model.to(device).eval()
            self._model, self._config, self._metadata, self._device, self._loaded_mtime_ns = model, config, checkpoint, device, mtime_ns
        finally:
            self._is_loading = False

    def predict_image(self, image_bytes: bytes, *, source: str, observation_id: str | None = None) -> IntensityResult:
        self._load()
        assert self._model is not None and self._config is not None and self._device is not None
        try:
            import torch
        except ImportError as exc:
            raise ModelDependencyError("PyTorch is not installed.") from exc
        tensor = image_bytes_to_tensor(image_bytes, image_size=self._config.image_size).unsqueeze(0).to(self._device)
        with torch.inference_mode():
            output = self._model(tensor)
            values = torch.softmax(output["classification_logits"], dim=1)[0].detach().cpu().tolist()
        labels = self._metadata["label_mapping"]["labels"]
        probabilities = {label: float(values[index]) for index, label in enumerate(labels)}
        category = max(probabilities, key=probabilities.get)
        statistics = self._metadata["target_statistics"]

        def restore(target: str) -> float | None:
            if target not in output:
                return None
            target_stats = statistics[target]
            normalized = float(output[target][0].detach().cpu().item())
            return normalized * float(target_stats["std"]) + float(target_stats["mean"])

        return IntensityResult(
            status="success", category=category, confidence=probabilities[category], class_probabilities=probabilities,
            wind_speed_kmh=restore("wind"), central_pressure_hpa=restore("pressure"),
            model_version=str(self._metadata["model_version"]), architecture=self._config.backbone,
            dataset_version=self._config.dataset_version, inference_timestamp_utc=datetime.now(timezone.utc),
            observation_id=observation_id, source=source,
        )


_service: IntensityService | None = None


def get_intensity_service() -> IntensityService:
    global _service
    if _service is None:
        _service = IntensityService()
    return _service
