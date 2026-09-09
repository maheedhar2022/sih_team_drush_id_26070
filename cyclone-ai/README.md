# CycloneAI

CycloneAI is a research-oriented North Indian Ocean cyclone monitoring application.
It presents observed tracks, official forecast tracks when an authoritative provider
supplies them, and satellite layer provenance. It does not generate AI predictions.

## Architecture

External providers flow through validation and normalisation before persistence:

`provider -> validation -> PostgreSQL/SQLite -> FastAPI -> React + MapLibre`

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
Render Blueprint for `backend/`.

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

Set `VITE_API_URL=https://your-render-service.onrender.com` in Vercel as a
Config variable, then redeploy the frontend.

## Data Behaviour

`GET /api/cyclones/active` returns real recent North Indian Ocean observations
when the source provides them. If none are active, the application displays a
clearly labelled historical AMPHAN 2020 record. Historical data is never
labelled as live.

See [Data Sources and Provenance](docs/data-sources-provenance.md) for sources,
credentials, freshness, and known limitations.

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
