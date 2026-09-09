# Phase 5 — Intensity Dataset Requirements

This directory is where the assembled intensity training dataset lives.
The directory currently contains only a `label_mapping.json` template.
**No model will be trained and no inference will be served until this dataset is assembled.**
The system correctly returns `MODEL_NOT_TRAINED` when no checkpoint exists.

---

## Why No Dataset is Included

A legitimate, openly-distributable, image-labelled intensity dataset for Indian Ocean
tropical cyclones does not exist in a single, publicly downloadable archive. The data
must be assembled from separate sources:

| Piece | Source |
|---|---|
| Satellite imagery | NASA Worldview / GIBS, MOSDAC (with access), NOAA CLASS |
| Cyclone best-track + intensity | IBTrACS v04r01 (NOAA NCEI — free) |

**We do not fabricate images, labels, or metrics.** Per the Phase 5 contract,
the system returns `MODEL_NOT_TRAINED` until real data is supplied.

---

## Dataset Format

The training pipeline reads a **manifest CSV** with the following columns:

| Column | Required | Description |
|---|---|---|
| `image_path` | Yes | Absolute or relative-to-manifest path to the image |
| `intensity_category` | Yes | Must exactly match a label in `label_mapping.json` |
| `source` | Yes | Data source identifier (e.g. `nasa_gibs`, `mosdac`) |
| `image_timestamp_utc` | Yes | ISO-8601 UTC timestamp of the satellite observation |
| `label_timestamp_utc` | Yes | ISO-8601 UTC timestamp of the best-track record used |
| `latitude` | Yes | Storm centre latitude at image time |
| `longitude` | Yes | Storm centre longitude at image time |
| `cyclone_id` | Yes | Unique cyclone / event identifier (e.g. `AMPHAN_2020`) |
| `split` | Yes | `train`, `val`, or `test` |
| `wind_speed_kmh` | No | 3-min sustained wind from best-track (km/h) |
| `central_pressure_hpa` | No | Central pressure from best-track (hPa) |

### Temporal Alignment Tolerance

The default matching tolerance is **30 minutes** (configurable via
`--timestamp-tolerance-minutes`). The validator rejects records where
`|image_timestamp_utc − label_timestamp_utc| > tolerance`.

### Event-Level Split (No Data Leakage)

**All observations from the same cyclone must go into one split only.**
The validator rejects manifests where the same `cyclone_id` appears in
more than one of `train`, `val`, `test`.

Example allocation:
```
train: AMPHAN_2020, NISARGA_2020, YAAS_2021, ASANI_2022, BIPARJOY_2023
val:   FANI_2019, BULBUL_2019
test:  TITLI_2018, GAJA_2018
```

---

## How to Assemble the Dataset

### Step 1 — Download IBTrACS best-track data

```bash
# North Indian Ocean full record (free, no auth required)
curl -L "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/ibtracs.NI.list.v04r01.csv" \
  -o data/cyclone_intensity/ibtracs_NI.csv
```

IBTrACS provides storm IDs, timestamps, locations, and agency-specific wind and
pressure fields. The builder uses only New Delhi/IMD-compatible 3-minute wind
observations when constructing an IMD intensity label.

### Step 2 — Use IMD/New Delhi wind observations only

IMD intensity scale based on 3-min sustained surface wind:

| IMD Category | Wind speed range |
|---|---|
| Depression | 31–49 km/h |
| Deep Depression | 50–61 km/h |
| Cyclonic Storm | 62–87 km/h |
| Severe Cyclonic Storm | 88–117 km/h |
| Very Severe Cyclonic Storm | 118–166 km/h |
| Extremely Severe Cyclonic Storm | 167–220 km/h |
| Super Cyclonic Storm | ≥ 221 km/h |

Use `NEWDELHI_WIND` / `NEW_WIND`. These are compatible with the IMD 3-minute
scale. `USA_WIND` is a 1-minute wind and must not be silently converted into an
IMD label. `WMO_WIND` is accepted only when `WMO_AGENCY` identifies New Delhi
or IMD.

### Step 3 — Download matching satellite imagery

#### Option A — NASA GIBS (public visual reference)

GIBS daily mosaics are useful for visual review, but their daily timestamp is
not an acquisition time precise enough for the default 30-minute label-alignment
requirement. Do not use a GIBS daily tile as a training sample without the
source granule's actual UTC acquisition time in the satellite catalog.

```python
# Example: MODIS Corrected Reflectance True Color (1 km, daily)
# GIBS WMTS endpoint documented at: https://wiki.earthdata.nasa.gov/display/GIBS
layer = "MODIS_Terra_CorrectedReflectance_TrueColor"
date  = "2020-05-20"  # match IBTrACS timestamp date
# Then clip to a 512×512 px box centred on the storm eye
```

Use a source-product catalog containing the actual acquisition time, locally
stored image path, source name, and IBTrACS `SID`. MOSDAC products with their
metadata or NASA source granules meet this requirement.

#### Option B — MOSDAC / INSAT-3D (requires registered access)

1. Register at https://www.mosdac.gov.in
2. Request research access for historical INSAT-3D imagery
3. Download IR and WV channel products for storm dates
4. Clip to 512×512 px centred on the eye (or 1° buffer around storm centre)

**Do not fabricate INSAT imagery. If MOSDAC access is unavailable, use NASA GIBS.**

### Step 4 — Build the manifest CSV

Use the supplied builder instead of creating labels manually. It rejects
incompatible 1-minute USA winds, performs timestamp alignment, creates an
event-level split, writes the train/validation/test IDs, and generates a label
mapping containing only categories actually present:

```bash
cd cyclone-ai/backend

python -m ai.training.build_intensity_manifest \
  --ibtracs ../data/cyclone_intensity/ibtracs_NI.csv \
  --satellite-catalog ../data/cyclone_intensity/satellite_catalog.csv \
  --output-dir ../data/cyclone_intensity/assembled \
  --timestamp-tolerance-minutes 30 \
  --seed 42
```

`satellite_catalog.csv` requires `image_path`, `source`,
`image_timestamp_utc`, and `cyclone_id`. Its timestamp must be the product's
actual acquisition time, never a download time or daily mosaic date.

### Manual manifest format

```python
import csv
from pathlib import Path

rows = []
for record in ibtracs_records:           # rows already aligned + labelled
    image_path = Path(f"images/{record.storm_id}_{record.timestamp:%Y%m%dT%H%M}.jpg")
    if not image_path.is_file():
        continue                         # skip if imagery download failed
    rows.append({
        "image_path":           str(image_path),
        "intensity_category":   record.imd_category,
        "source":               "nasa_gibs",
        "image_timestamp_utc":  record.timestamp.isoformat(),
        "label_timestamp_utc":  record.timestamp.isoformat(),  # same record
        "latitude":             record.lat,
        "longitude":            record.lon,
        "cyclone_id":           record.storm_id,
        "split":                record.split,          # assign by cyclone_id
        "wind_speed_kmh":       record.wind_kmh,
        "central_pressure_hpa": record.pressure_hpa,
    })

with open("data/cyclone_intensity/manifest.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
```

### Step 5 — Validate the dataset before training

```bash
cd cyclone-ai/backend

python -m ai.training.validate_intensity_dataset \
  --manifest ../data/cyclone_intensity/manifest.csv \
  --label-mapping ../data/cyclone_intensity/label_mapping.json \
  --timestamp-tolerance-minutes 30
```

This validates: required columns, valid categories, event-level split integrity,
timestamp alignment, and image file existence. Fix all errors before proceeding.

### Step 6 — Train the model

```bash
cd cyclone-ai/backend

python -m ai.training.train_intensity \
  --manifest ../data/cyclone_intensity/manifest.csv \
  --label-mapping ../data/cyclone_intensity/label_mapping.json \
  --output-dir ../models/intensity \
  --backbone resnet18 \
  --epochs 30 \
  --batch-size 16 \
  --learning-rate 1e-4 \
  --image-size 224 \
  --seed 42 \
  --dataset-version imd-ni-v1 \
  --dataset-source "ibtracs_v04r01+nasa_gibs" \
  --device auto
```

The script saves `models/intensity/best.pt` when the validation loss improves.
The intensity service will automatically load this checkpoint on the next request.

---

## What the System Returns Without Training

```json
{
  "status": "MODEL_NOT_TRAINED",
  "dataset_status": "DATASET_UNAVAILABLE",
  "reason": "No intensity-labelled, event-split satellite dataset or trained intensity checkpoint is available.",
  "category": null,
  "wind_speed_kmh": null,
  "central_pressure_hpa": null
}
```

This is the correct and expected response until the above steps are completed.

---

## Minimum Dataset Size Guidance

| Category count | Recommended minimum images |
|---|---|
| 2 | ≥ 200 per category |
| 5+ | ≥ 150 per category |

With IBTrACS NI records since 1990 and 3-hourly imagery from GIBS, it is feasible
to assemble several thousand labelled records for the North Indian Ocean basin.
