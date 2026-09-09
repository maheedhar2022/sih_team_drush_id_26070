"""Configuration for the Phase 5 shared-backbone intensity model."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


SUPPORTED_BACKBONES = {"resnet18", "resnet50"}
SUPPORTED_OPTIMIZERS = {"adamw", "sgd"}
SUPPORTED_SCHEDULERS = {"plateau", "none"}


@dataclass(frozen=True)
class IntensityConfig:
    backbone: str = "resnet18"
    image_size: int = 224
    batch_size: int = 16
    epochs: int = 20
    learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    seed: int = 42
    patience: int = 5
    pretrained: bool = True
    dataset_version: str = "unconfigured"
    dataset_source: str = "unconfigured"
    timestamp_tolerance_minutes: int = 30
    wind_loss_weight: float = 1.0
    pressure_loss_weight: float = 1.0
    optimizer: str = "adamw"
    scheduler: str = "plateau"

    def __post_init__(self) -> None:
        if self.backbone not in SUPPORTED_BACKBONES:
            raise ValueError(f"backbone must be one of {sorted(SUPPORTED_BACKBONES)}")
        if self.optimizer not in SUPPORTED_OPTIMIZERS:
            raise ValueError(f"optimizer must be one of {sorted(SUPPORTED_OPTIMIZERS)}")
        if self.scheduler not in SUPPORTED_SCHEDULERS:
            raise ValueError(f"scheduler must be one of {sorted(SUPPORTED_SCHEDULERS)}")
        if self.image_size < 32 or self.batch_size < 1 or self.epochs < 1 or self.patience < 1:
            raise ValueError("image_size, batch_size, epochs, and patience must be positive")
        if self.learning_rate <= 0 or self.wind_loss_weight < 0 or self.pressure_loss_weight < 0:
            raise ValueError("learning rate and loss weights must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IntensityConfig":
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in payload.items() if key in allowed})


def default_model_path(model_root: str | Path) -> Path:
    return Path(model_root) / "intensity" / "best.pt"

