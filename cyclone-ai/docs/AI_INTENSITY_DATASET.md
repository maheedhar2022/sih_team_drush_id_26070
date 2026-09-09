# CycloneAI Phase 5 Intensity Dataset

## Current status

No intensity-labelled satellite-image dataset, label mapping, or intensity model
checkpoint is present in this repository. Consequently, `/api/ai/intensity/status`
reports `MODEL_NOT_TRAINED` with `dataset_status: DATASET_UNAVAILABLE`, and the
application does not show a category, confidence, wind, or pressure estimate.

The Phase 4 cyclone/no-cyclone manifest cannot be repurposed for Phase 5 because
it has neither authoritative intensity labels nor matched wind/pressure targets.

## Required provenance

Before collecting or training data, preserve the dataset owner, access location,
version, licence or permission, image product, sensor/channel, geographic coverage,
and intensity-label authority. A usable record must connect an actual satellite
image to a contemporaneous best-track or operational observation. Suitable label
authorities may include the dataset's documented agency source, such as IMD/RSMC
or IBTrACS, but their category systems and wind conventions must be recorded rather
than assumed.

CycloneAI stores wind in `km/h` and pressure in `hPa`. If a source provides knots
or metres per second, dataset preparation must record and explicitly convert the
source unit before producing the manifest. The training code does not guess units.

## Required files

`label_mapping.json` establishes the authoritative, ordered category list:

```json
{
  "label_system": "Documented source classification scale",
  "source": "Dataset owner and authoritative label authority",
  "dataset_version": "intensity-dataset-v1",
  "labels": ["Depression", "Deep Depression", "Cyclonic Storm"]
}
```

These labels are only a structural example. Replace them with the exact documented
labels supplied by the selected dataset; do not infer category thresholds.

`manifest.csv` must include:

```csv
image_path,intensity_category,source,image_timestamp_utc,label_timestamp_utc,latitude,longitude,cyclone_id,split,wind_speed_kmh,central_pressure_hpa
images/example.png,Cyclonic Storm,research_dataset,2020-05-18T18:00:00Z,2020-05-18T18:00:00Z,14.5,86.3,AMPHAN_2020,train,120,970
```

- `cyclone_id` is an event identity. Every event belongs to exactly one of
  `train`, `val`, or `test`.
- Image and label timestamps must be timezone-aware ISO UTC values. The default
  matching tolerance is 30 minutes and is configurable.
- Wind and pressure may be blank only when genuinely unavailable. A regression
  head is created only for targets present in the training split.

## Validation and training

From `backend/`, after placing licensed data outside Git:

```bash
python -m ai.training.validate_intensity_dataset \
  --manifest ../data/cyclone_intensity/manifest.csv \
  --label-mapping ../data/cyclone_intensity/label_mapping.json

python -m ai.training.train_intensity \
  --manifest ../data/cyclone_intensity/manifest.csv \
  --label-mapping ../data/cyclone_intensity/label_mapping.json \
  --dataset-version intensity-dataset-v1 \
  --dataset-source "documented dataset source"
```

The shared ResNet baseline writes `best.pt`, `last.pt`, `config.json`,
`label_mapping.json`, `training_history.json`, and `metrics.json` under
`models/intensity/`. It uses held-out cyclone events for the final test evaluation.
Classification metrics include macro precision, macro recall, macro/weighted F1,
per-class metrics, and a confusion matrix. Wind and pressure metrics include MAE,
RMSE, and R2 with explicit units.

AI-generated analysis is experimental and for research and education only. It is
not a substitute for official meteorological warnings or emergency guidance.

