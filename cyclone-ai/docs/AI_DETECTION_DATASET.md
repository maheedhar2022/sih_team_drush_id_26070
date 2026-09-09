# CycloneAI Phase 4 Detection Dataset

## Current status

No licensed, labelled satellite-image cyclone detection dataset is present in this
repository. No model checkpoint has been trained, and the application therefore
returns `MODEL_NOT_TRAINED`; it does not generate a substitute prediction.

Do not commit image collections or model checkpoints to Git. Store them in approved
research storage and retain the source licence and access conditions with the data.

## Required dataset

The detector expects a CSV manifest with the following columns:

```csv
image_path,label,source,timestamp,latitude,longitude,cyclone_id,split
images/amphan-001.png,cyclone,research_dataset,2020-05-18T18:00:00Z,14.5,86.3,AMPHAN_2020,train
images/background-001.png,no_cyclone,research_dataset,2020-05-18T18:00:00Z,10.2,82.0,BOB_BACKGROUND_20200518,test
```

- `label` is exactly `cyclone` or `no_cyclone`.
- `source` identifies the originating provider or research dataset.
- `cyclone_id` is the storm/event group. For a non-cyclone image, use a stable
  scene/event group ID rather than leaving it blank.
- `split` is exactly `train`, `val`, or `test`.
- `image_path` is relative to the manifest location unless an approved absolute
  path is intentionally used for offline training.

The CSV format is required for training because it preserves provenance and
event-group identity. A simple class-folder structure is not sufficient to prove
that adjacent images from the same storm have not leaked into multiple splits.

## Split policy

CycloneAI validates that one `cyclone_id` appears in exactly one split. This means
all AMPHAN images must be in train, validation, or test, never several of them.
The held-out `test` split is evaluated once after best-checkpoint selection and is
not used for tuning.

## Data acceptance checklist

Before training, record:

1. Dataset owner, access URL, version, and licence or written usage permission.
2. Satellite/sensor, product/channel, geographic and temporal coverage.
3. Image count, dimensions, file formats, and class/event distribution.
4. The event-level split assignment and all held-out test event IDs.

Use only image products that the source licence permits for machine-learning
research. MOSDAC/INSAT remains the intended operational source, but it is not a
training input until authorised source products and labels are available.

## Training

From `backend/`, after installing the requirements and placing a validated
manifest outside Git:

```bash
python -m ai.training.validate_detection_dataset \
  --manifest ../data/cyclone_detection/manifest.csv

python -m ai.training.train_detection \
  --manifest ../data/cyclone_detection/manifest.csv \
  --dataset-version cyclone-detection-v1 \
  --model resnet18
```

The command writes `best.pt`, `last.pt`, `config.json`, `training_history.json`,
and `evaluation.json` to `models/detection/`. It uses CUDA when available and CPU
otherwise. The first baseline is ResNet-18 because it is practical on CPU; use
`--model resnet50` only after the dataset size and training environment justify it.
