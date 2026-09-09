"""In-memory inference service for a trained cyclone detector."""
from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings

from .config import CLASS_TO_INDEX, DetectionConfig, default_model_path
from .model import build_model
from .preprocessing import image_bytes_to_tensor


class ModelNotTrainedError(RuntimeError):
    """Raised when inference is requested before a real checkpoint exists."""


class ModelDependencyError(RuntimeError):
    """Raised when a checkpoint exists but its runtime dependencies are absent."""


@dataclass(frozen=True)
class DetectionStatus:
    status: str
    model_version: str | None
    architecture: str | None
    dataset_version: str | None
    reason: str | None


@dataclass(frozen=True)
class DetectionResult:
    status: str
    prediction: str
    confidence: float
    cyclone_probability: float
    no_cyclone_probability: float
    model_version: str
    architecture: str
    dataset_version: str
    inference_timestamp_utc: datetime
    observation_id: str | None
    source: str


class DetectionService:
    """Keeps one validated model checkpoint in memory per process."""

    def __init__(self, model_root: str | Path | None = None, device: str | None = None) -> None:
        settings = get_settings()
        self.model_root = Path(model_root or settings.ai_model_dir).expanduser()
        self.requested_device = device or settings.ai_device
        self._loaded_path: Path | None = None
        self._loaded_mtime_ns: int | None = None
        self._model: Any | None = None
        self._config: DetectionConfig | None = None
        self._metadata: dict[str, Any] = {}
        self._device: Any | None = None

    @property
    def checkpoint_path(self) -> Path:
        return default_model_path(self.model_root)

    def status(self) -> DetectionStatus:
        path = self.checkpoint_path
        if not path.is_file():
            return DetectionStatus(
                status="MODEL_NOT_TRAINED",
                model_version=None,
                architecture=None,
                dataset_version=None,
                reason="No trained detection checkpoint is available.",
            )
        try:
            import torch  # noqa: F401
            import torchvision  # noqa: F401
            import PIL  # noqa: F401
        except ImportError:
            return DetectionStatus(
                status="DEPENDENCY_UNAVAILABLE",
                model_version=None,
                architecture=None,
                dataset_version=None,
                reason="The checkpoint exists but PyTorch, Torchvision, or Pillow is not installed.",
            )
        return DetectionStatus(
            status="READY",
            model_version=self._metadata.get("model_version") if self._metadata else None,
            architecture=self._config.model_name if self._config else None,
            dataset_version=self._config.dataset_version if self._config else None,
            reason=None,
        )

    def _select_device(self) -> Any:
        try:
            import torch
        except ImportError as exc:
            raise ModelDependencyError("PyTorch is not installed.") from exc
        if self.requested_device == "cpu":
            return torch.device("cpu")
        if self.requested_device == "cuda":
            if not torch.cuda.is_available():
                raise ModelDependencyError("AI_DEVICE=cuda was requested but CUDA is unavailable.")
            return torch.device("cuda")
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _load_model(self) -> None:
        path = self.checkpoint_path
        if not path.is_file():
            raise ModelNotTrainedError("No trained detection checkpoint is available.")
        mtime_ns = path.stat().st_mtime_ns
        if self._model is not None and self._loaded_path == path and self._loaded_mtime_ns == mtime_ns:
            return
        try:
            import torch
        except ImportError as exc:
            raise ModelDependencyError("PyTorch is not installed.") from exc

        device = self._select_device()
        try:
            checkpoint = torch.load(path, map_location=device, weights_only=False)
        except TypeError:  # Compatibility with supported older Torch releases.
            checkpoint = torch.load(path, map_location=device)
        if not isinstance(checkpoint, dict) or "state_dict" not in checkpoint or "config" not in checkpoint:
            raise ModelNotTrainedError("Detection checkpoint is incomplete or incompatible.")

        config = DetectionConfig.from_dict(checkpoint["config"])
        model_version = checkpoint.get("model_version")
        if not isinstance(model_version, str) or not model_version.strip():
            raise ModelNotTrainedError("Detection checkpoint is missing its model version.")

        model = build_model(config, use_pretrained_weights=False)
        model.load_state_dict(checkpoint["state_dict"])
        model.to(device)
        model.eval()

        self._model = model
        self._config = config
        self._metadata = checkpoint
        self._device = device
        self._loaded_path = path
        self._loaded_mtime_ns = mtime_ns

    def predict_image(self, image_bytes: bytes, *, source: str, observation_id: str | None = None) -> DetectionResult:
        self._load_model()
        assert self._model is not None and self._config is not None and self._device is not None
        try:
            import torch
        except ImportError as exc:
            raise ModelDependencyError("PyTorch is not installed.") from exc

        tensor = image_bytes_to_tensor(image_bytes, image_size=self._config.image_size).unsqueeze(0).to(self._device)
        with torch.inference_mode():
            probabilities = torch.softmax(self._model(tensor), dim=1)[0].detach().cpu().tolist()

        no_cyclone_probability = float(probabilities[CLASS_TO_INDEX["no_cyclone"]])
        cyclone_probability = float(probabilities[CLASS_TO_INDEX["cyclone"]])
        prediction = "cyclone" if cyclone_probability >= no_cyclone_probability else "no_cyclone"
        confidence = cyclone_probability if prediction == "cyclone" else no_cyclone_probability
        return DetectionResult(
            status="success",
            prediction=prediction,
            confidence=confidence,
            cyclone_probability=cyclone_probability,
            no_cyclone_probability=no_cyclone_probability,
            model_version=str(self._metadata["model_version"]),
            architecture=self._config.model_name,
            dataset_version=self._config.dataset_version,
            inference_timestamp_utc=datetime.now(timezone.utc),
            observation_id=observation_id,
            source=source,
        )

    @staticmethod
    def runtime_metadata() -> dict[str, str]:
        import platform

        metadata = {"python": platform.python_version()}
        for package in ("torch", "torchvision", "Pillow"):
            try:
                metadata[package.lower()] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                metadata[package.lower()] = "not installed"
        return metadata


_service: DetectionService | None = None


def get_detection_service() -> DetectionService:
    global _service
    if _service is None:
        _service = DetectionService()
    return _service
