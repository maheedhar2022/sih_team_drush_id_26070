"""Shared ResNet backbone with intensity-category and optional regression heads."""
from __future__ import annotations

from typing import Any

from .config import IntensityConfig


def build_model(
    config: IntensityConfig,
    *,
    num_categories: int,
    predict_wind: bool,
    predict_pressure: bool,
    use_pretrained_weights: bool,
) -> Any:
    """Build only the heads supported by the labels in the training dataset."""
    try:
        import torch.nn as nn
        from torchvision.models import ResNet18_Weights, ResNet50_Weights, resnet18, resnet50
    except ImportError as exc:
        raise RuntimeError("Intensity modelling requires torch and torchvision.") from exc
    if num_categories < 2:
        raise ValueError("At least two intensity categories are required")
    if config.backbone == "resnet50":
        backbone = resnet50(weights=ResNet50_Weights.DEFAULT if use_pretrained_weights else None)
    else:
        backbone = resnet18(weights=ResNet18_Weights.DEFAULT if use_pretrained_weights else None)
    feature_size = backbone.fc.in_features
    backbone.fc = nn.Identity()

    class SharedIntensityModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.backbone = backbone
            self.classification_head = nn.Linear(feature_size, num_categories)
            self.wind_head = nn.Linear(feature_size, 1) if predict_wind else None
            self.pressure_head = nn.Linear(feature_size, 1) if predict_pressure else None

        def forward(self, images: Any) -> dict[str, Any]:
            features = self.backbone(images)
            output = {"classification_logits": self.classification_head(features)}
            if self.wind_head is not None:
                output["wind"] = self.wind_head(features).squeeze(1)
            if self.pressure_head is not None:
                output["pressure"] = self.pressure_head(features).squeeze(1)
            return output

    return SharedIntensityModel()

