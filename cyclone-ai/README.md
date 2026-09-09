# CycloneAI

CycloneAI is a research-oriented North Indian Ocean cyclone monitoring application.
It presents observed tracks, official forecast tracks when an authoritative provider
supplies them, satellite layer provenance, and a Phase 4 image-classification
baseline. It does not perform track, intensity, or movement prediction.

## Architecture

External providers flow through validation and normalisation before persistence:

`provider -> validation -> PostgreSQL/SQLite -> FastAPI -> React + MapLibre`

The optional detection path is separate and never supplies an official warning:

`licensed satellite image -> preprocessing -> trained ResNet -> detection API`

The React client only calls the FastAPI API. It never calls meteorological data
providers directly.

## Run Locally

Backend:

```bash
cd backend
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend, in another terminal:

```bash
cd frontend
npm ci
npm run dev
```

The frontend runs at `http://localhost:5173` and proxies API requests to the
backend during development. Copy `.env.example` to `.env` before changing any
backend configuration.

## Deployment

The repository root contains the Vercel configuration for `frontend/` and a
Render Blueprint for `backend/`. See [Satellite Data Pipeline](docs/SATELLITE_DATA.md)
before enabling MOSDAC downloads in a deployed environment.

Render service settings:

```text
Root Directory: cyclone-ai/backend
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health Check Path: /api/health
PYTHON_VERSION: 3.12.11
```

Required production variables:

```text
APP_ENV=production
DATABASE_URL=postgresql+asyncpg://...
CORS_ORIGINS=["https://your-vercel-project.vercel.app"]
```

Phase 4 model settings:

```text
AI_MODEL_DIR=../models
AI_DEVICE=auto
AI_MAX_IMAGE_MB=10
```

`AI_MODEL_DIR/detection/best.pt` is intentionally absent until a licensed,
event-split dataset has been trained. Without it, the API reports
`MODEL_NOT_TRAINED` and the UI shows an unavailable state.

Optional MOSDAC source-product discovery requires these backend-only variables:

```text
MOSDAC_ENABLED=true
SATELLITE_ADMIN_TOKEN=<long-random-secret>
```

Leave `MOSDAC_DOWNLOAD_ENABLED=false` until the service has persistent storage
and the team has validated a real HDF sample.

Set `VITE_API_URL=https://your-render-service.onrender.com` in Vercel as a
Config variable, then redeploy the frontend.

## Data Behaviour

`GET /api/cyclones/active` returns real recent North Indian Ocean observations
when the source provides them. If none are active, the application displays a
clearly labelled historical AMPHAN 2020 record. Historical data is never
labelled as live.

See [Data Sources and Provenance](docs/data-sources-provenance.md) for sources,
credentials, freshness, and known limitations.

See [AI Detection Dataset](docs/AI_DETECTION_DATASET.md) for the required
manifest, licence/provenance record, event-level split policy, and training run.

See [AI Intensity Dataset](docs/AI_INTENSITY_DATASET.md) for the separate
intensity-category and wind/pressure dataset contract. A cyclone/no-cyclone
dataset cannot be used to train the Phase 5 model.

## Tests

```bash
cd backend
pytest -q

cd ../frontend
npm run build
```

## API

- `GET /api/health`
- `GET /api/cyclones`
- `GET /api/cyclones/active`
- `GET /api/cyclones/{cyclone_id}`
- `GET /api/cyclones/{cyclone_id}/track`
- `GET /api/cyclones/{cyclone_id}/forecast`
- `GET /api/data-sources`
- `GET /api/satellite/latest`
- `GET /api/satellite/layers`
- `GET /api/satellite/status`
- `GET /api/satellite/observations`
- `POST /api/satellite/mosdac/discover` (admin token required)
- `POST /api/satellite/observations/{id}/download` (admin token and explicit download enablement required)
- `GET /api/ai/detection/status`
- `POST /api/ai/detection?source=<source>&observation_id=<optional-id>`
- `GET /api/ai/intensity/status`
- `POST /api/ai/intensity?source=<source>&observation_id=<optional-id>`
