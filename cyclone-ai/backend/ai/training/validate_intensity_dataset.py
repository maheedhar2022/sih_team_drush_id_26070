"""Validate a Phase 5 dataset before installing ML dependencies or training."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai.intensity.dataset import IntensityDatasetError, load_label_mapping, load_manifest, validate_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate an event-split intensity dataset")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--label-mapping", type=Path, required=True)
    parser.add_argument("--timestamp-tolerance-minutes", type=int, default=30)
    args = parser.parse_args()
    try:
        report = validate_records(load_manifest(args.manifest, load_label_mapping(args.label_mapping)), timestamp_tolerance_minutes=args.timestamp_tolerance_minutes)
    except IntensityDatasetError as exc:
        raise SystemExit(f"Intensity dataset validation failed: {exc}") from exc
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()

