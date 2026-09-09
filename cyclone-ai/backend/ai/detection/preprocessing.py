"""Image loading and deterministic validation/inference preprocessing."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any


IMAGE_MEAN = (0.485, 0.456, 0.406)
IMAGE_STD = (0.229, 0.224, 0.225)
MAX_IMAGE_PIXELS = 40_000_000


class ImagePreprocessingError(ValueError):
    """An image cannot safely be used by the detector."""


def _image_dependencies() -> tuple[Any, Any]:
    try:
        from PIL import Image, UnidentifiedImageError
        from torchvision import transforms
    except ImportError as exc:
        raise RuntimeError(
            "Image preprocessing requires Pillow and torchvision. "
            "Install backend/requirements.txt before training or inference."
        ) from exc
    return Image, (UnidentifiedImageError, transforms)


def build_transform(*, image_size: int, training: bool) -> Any:
    """Return augmented training or deterministic evaluation transforms."""
    _, (_, transforms) = _image_dependencies()
    common = [transforms.Resize((image_size, image_size)), transforms.ToTensor(), transforms.Normalize(IMAGE_MEAN, IMAGE_STD)]
    if not training:
        return transforms.Compose(common)
    return transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
        transforms.ColorJitter(brightness=0.08, contrast=0.08, saturation=0.05),
        transforms.ToTensor(),
        transforms.Normalize(IMAGE_MEAN, IMAGE_STD),
    ])


def open_rgb_image(image_bytes: bytes) -> Any:
    """Decode and validate an uploaded image without trusting its declared type."""
    Image, (UnidentifiedImageError, _) = _image_dependencies()
    if not image_bytes:
        raise ImagePreprocessingError("Image payload is empty")
    try:
        with Image.open(BytesIO(image_bytes)) as verification_image:
            verification_image.verify()
        with Image.open(BytesIO(image_bytes)) as decoded_image:
            if decoded_image.width * decoded_image.height > MAX_IMAGE_PIXELS:
                raise ImagePreprocessingError("Image dimensions exceed the 40 megapixel limit")
            return decoded_image.convert("RGB").copy()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImagePreprocessingError("File is not a valid supported image") from exc


def load_image_tensor(path: str | Path, *, image_size: int, training: bool) -> Any:
    image_path = Path(path)
    if not image_path.is_file():
        raise ImagePreprocessingError(f"Image does not exist: {image_path}")
    return build_transform(image_size=image_size, training=training)(open_rgb_image(image_path.read_bytes()))


def image_bytes_to_tensor(image_bytes: bytes, *, image_size: int) -> Any:
    return build_transform(image_size=image_size, training=False)(open_rgb_image(image_bytes))

