"""Torchvision ResNet transfer-learning baseline."""
from __future__ import annotations

from typing import Any

from .config import DetectionConfig


def build_model(config: DetectionConfig, *, use_pretrained_weights: bool) -> Any:
    """Build a two-class ResNet classifier; imports Torch only when used."""
    try:
        import torch.nn as nn
        from torchvision.models import ResNet18_Weights, ResNet50_Weights, resnet18, resnet50
    except ImportError as exc:
        raise RuntimeError(
            "Model construction requires torch and torchvision. "
            "Install backend/requirements.txt before training or inference."
        ) from exc

    if config.model_name == "resnet50":
        model = resnet50(weights=ResNet50_Weights.DEFAULT if use_pretrained_weights else None)
    else:
        model = resnet18(weights=ResNet18_Weights.DEFAULT if use_pretrained_weights else None)
    model.fc = nn.Linear(model.fc.in_features, 2)
    return model

