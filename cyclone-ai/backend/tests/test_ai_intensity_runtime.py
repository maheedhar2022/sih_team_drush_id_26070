"""Optional Torch runtime tests for the Phase 5 shared model."""
from __future__ import annotations

import pytest

try:
    import torch
    import torchvision  # noqa: F401
except Exception as exc:  # Native ML libraries can fail to initialise on unsupported Python builds.
    pytest.skip(f"PyTorch/Torchvision runtime is unavailable: {exc}", allow_module_level=True)

from ai.intensity.config import IntensityConfig
from ai.intensity.model import build_model


def test_shared_intensity_model_cpu_output_shapes():
    model = build_model(IntensityConfig(backbone="resnet18"), num_categories=3, predict_wind=True, predict_pressure=True, use_pretrained_weights=False).cpu().eval()
    with torch.inference_mode():
        output = model(torch.zeros((1, 3, 224, 224)))
    assert tuple(output["classification_logits"].shape) == (1, 3)
    assert tuple(output["wind"].shape) == (1,)
    assert tuple(output["pressure"].shape) == (1,)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available")
def test_shared_intensity_model_cuda_output_shapes():
    model = build_model(IntensityConfig(backbone="resnet18"), num_categories=3, predict_wind=False, predict_pressure=True, use_pretrained_weights=False).cuda().eval()
    with torch.inference_mode():
        output = model(torch.zeros((1, 3, 224, 224), device="cuda"))
    assert tuple(output["classification_logits"].shape) == (1, 3)
    assert "wind" not in output
    assert tuple(output["pressure"].shape) == (1,)

