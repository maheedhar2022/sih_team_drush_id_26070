"""Validate a Phase 4 manifest before installing Torch or starting training."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai.detection.dataset import DatasetValidationError, load_manifest, validate_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate an event-split cyclone detection manifest")
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = validate_records(load_manifest(args.manifest), check_images=True)
    except DatasetValidationError as exc:
        raise SystemExit(f"Dataset validation failed: {exc}") from exc
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

