"""Configuration shared by training and inference."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


CLASS_TO_INDEX = {"no_cyclone": 0, "cyclone": 1}
SUPPORTED_MODELS = {"resnet18", "resnet50"}


@dataclass(frozen=True)
class DetectionConfig:
    """Reproducible configuration for the first detector baseline."""

    model_name: str = "resnet18"
    image_size: int = 224
    batch_size: int = 16
    epochs: int = 20
    learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    seed: int = 42
    patience: int = 5
    pretrained: bool = True
    dataset_version: str = "unconfigured"

    def __post_init__(self) -> None:
        if self.model_name not in SUPPORTED_MODELS:
            raise ValueError(f"model_name must be one of {sorted(SUPPORTED_MODELS)}")
        if self.image_size < 32:
            raise ValueError("image_size must be at least 32 pixels")
        if self.batch_size < 1 or self.epochs < 1 or self.patience < 1:
            raise ValueError("batch_size, epochs, and patience must be positive")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DetectionConfig":
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in payload.items() if key in allowed})


def default_model_path(model_root: str | Path) -> Path:
    return Path(model_root) / "detection" / "best.pt"

