"""Manifest-based data validation with event-level leakage protection."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .config import CLASS_TO_INDEX


REQUIRED_MANIFEST_COLUMNS = {
    "image_path", "label", "source", "timestamp", "latitude", "longitude", "cyclone_id", "split",
}
VALID_SPLITS = {"train", "val", "test"}


class DatasetValidationError(ValueError):
    """The supplied detection dataset cannot be used safely."""


@dataclass(frozen=True)
class ManifestRecord:
    image_path: Path
    label: str
    source: str
    timestamp: str
    latitude: str
    longitude: str
    cyclone_id: str
    split: str


def load_manifest(manifest_path: str | Path) -> list[ManifestRecord]:
    """Load records while preserving each image's source and event identity."""
    path = Path(manifest_path)
    if not path.is_file():
        raise DatasetValidationError(f"Manifest does not exist: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = set(reader.fieldnames or [])
        missing = REQUIRED_MANIFEST_COLUMNS - headers
        if missing:
            raise DatasetValidationError(
                f"Manifest is missing required columns: {', '.join(sorted(missing))}"
            )

        records: list[ManifestRecord] = []
        for line_number, row in enumerate(reader, start=2):
            values = {key: (row.get(key) or "").strip() for key in REQUIRED_MANIFEST_COLUMNS}
            if not values["image_path"]:
                raise DatasetValidationError(f"Row {line_number}: image_path is required")
            if values["label"] not in CLASS_TO_INDEX:
                raise DatasetValidationError(
                    f"Row {line_number}: label must be cyclone or no_cyclone"
                )
            if values["split"] not in VALID_SPLITS:
                raise DatasetValidationError(
                    f"Row {line_number}: split must be train, val, or test"
                )
            if not values["source"] or not values["cyclone_id"]:
                raise DatasetValidationError(
                    f"Row {line_number}: source and cyclone_id/event group are required"
                )

            raw_image_path = Path(values["image_path"])
            image_path = raw_image_path if raw_image_path.is_absolute() else path.parent / raw_image_path
            values["image_path"] = image_path.resolve()
            records.append(ManifestRecord(**values))

    if not records:
        raise DatasetValidationError("Manifest does not contain any image records")
    return records


def validate_records(records: list[ManifestRecord], *, check_images: bool = True) -> dict[str, object]:
    """Validate files and ensure one cyclone/event never spans dataset splits."""
    events: dict[str, set[str]] = defaultdict(set)
    missing_images: list[str] = []
    label_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()

    for record in records:
        events[record.cyclone_id].add(record.split)
        label_counts[record.label] += 1
        split_counts[record.split] += 1
        if check_images and not record.image_path.is_file():
            missing_images.append(str(record.image_path))

    leaked_events = sorted(event for event, splits in events.items() if len(splits) > 1)
    if leaked_events:
        preview = ", ".join(leaked_events[:5])
        raise DatasetValidationError(
            "Event-level data leakage: the same cyclone/event is in multiple splits "
            f"({preview}). Split by cyclone_id before training."
        )
    if missing_images:
        preview = ", ".join(missing_images[:3])
        raise DatasetValidationError(f"Manifest references missing image files: {preview}")
    if len(label_counts) < 2:
        raise DatasetValidationError("Both cyclone and no_cyclone classes are required")
    if not split_counts.get("train") or not split_counts.get("val") or not split_counts.get("test"):
        raise DatasetValidationError("Train, val, and test splits must each contain at least one image")

    return {
        "image_count": len(records),
        "class_distribution": dict(sorted(label_counts.items())),
        "split_distribution": dict(sorted(split_counts.items())),
        "event_count": len(events),
        "events_by_split": {
            split: sorted(event for event, event_splits in events.items() if split in event_splits)
            for split in sorted(VALID_SPLITS)
        },
    }


def records_for_split(records: list[ManifestRecord], split: str) -> list[ManifestRecord]:
    if split not in VALID_SPLITS:
        raise ValueError(f"Unknown split: {split}")
    return [record for record in records if record.split == split]
