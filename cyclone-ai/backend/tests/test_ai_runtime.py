"""Tests activated in environments with the optional Phase 4 ML stack."""
from __future__ import annotations

import pytest

try:
    import torch
    import torchvision  # noqa: F401
    from PIL import Image
except Exception as exc:  # Native ML libraries can fail to initialise on unsupported Python builds.
    pytest.skip(f"PyTorch/Torchvision runtime is unavailable: {exc}", allow_module_level=True)

from ai.detection.config import DetectionConfig
from ai.detection.model import build_model
from ai.detection.preprocessing import image_bytes_to_tensor


def test_validation_preprocessing_is_deterministic(tmp_path):
    image_path = tmp_path / "fixture.png"
    Image.new("RGB", (24, 16), color=(32, 64, 128)).save(image_path)
    payload = image_path.read_bytes()
    first = image_bytes_to_tensor(payload, image_size=64)
    second = image_bytes_to_tensor(payload, image_size=64)
    assert tuple(first.shape) == (3, 64, 64)
    assert torch.equal(first, second)


def test_resnet18_cpu_output_dimensions():
    model = build_model(DetectionConfig(model_name="resnet18"), use_pretrained_weights=False).cpu().eval()
    with torch.inference_mode():
        output = model(torch.zeros((1, 3, 224, 224)))
    assert tuple(output.shape) == (1, 2)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA is not available")
def test_resnet18_cuda_output_dimensions():
    model = build_model(DetectionConfig(model_name="resnet18"), use_pretrained_weights=False).cuda().eval()
    with torch.inference_mode():
        output = model(torch.zeros((1, 3, 224, 224), device="cuda"))
    assert tuple(output.shape) == (1, 2)

