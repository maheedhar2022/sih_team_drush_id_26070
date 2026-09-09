# Satellite Data Pipeline

CycloneAI treats a satellite image as a source product with a processing
history, not as an arbitrary picture on the map.

## Sources

- NASA GIBS provides the existing public MapLibre raster overlays. Each tile is
  fetched with a source date and is never represented as an INSAT product.
- MOSDAC is the preferred source for INSAT-3DS Imager L1B Standard
  (`3SIMG_L1B_STD`). INSAT-3DR Imager L1B Standard (`3RIMG_L1B_STD`) is a
  secondary source when 3DS is unavailable.

MOSDAC search requests are public. Downloads require a MOSDAC account and use
the official flow: search -> bearer-token authentication -> download by the
source granule `id` -> logout. The official manual limits a search request to
100 results and a user to 5,000 downloads per day.

Official reference: <https://www.mosdac.gov.in/downloadapi-manual>

## Storage Contract

`SATELLITE_STORAGE_DIR` contains product bytes. Its default local layout is:

```text
data/satellite/
  raw/<source>/<product>/<YYYY>/<MM>/<DD>/
  processed/<source>/<product>/<YYYY>/<MM>/<DD>/
  thumbnails/<source>/<product>/<YYYY>/<MM>/<DD>/
  tiles/<source>/<product>/<YYYY>/<MM>/<DD>/
```

The database stores only relative paths, SHA-256, source metadata, timestamps,
and processing status. Never store HDF product bytes in PostgreSQL. Render's
ephemeral filesystem is unsuitable for retained products; use a persistent disk
or object storage before enabling a download worker in production.

## Product Lifecycle

1. Discover an exact MOSDAC product and record its source granule identity.
2. Download the original product to `raw/`; retain the source filename and
   compute a SHA-256 checksum.
3. Validate file type and read actual product metadata. Do not infer a channel,
   timestamp, geostationary projection, geographic extent, or resolution from a
   filename.
4. Record the observation in `satellite_observations` as `DOWNLOADED`.
5. Only after a representative sample is validated, render a channel-specific
   derived web image and record `PROCESSED` with its `web_asset_path`.
6. The FastAPI image endpoint serves only a `PROCESSED` asset that resolves
   within the configured storage root. Otherwise it returns an explicit 404.

No worker automatically downloads MOSDAC products yet. That is intentional:
the first real product sample must establish the HDF fields, calibration,
projection, and georeferencing rules before an INSAT image can be rendered or
offered as a map overlay.

## API

- `GET /api/satellite/status` reports catalog readiness without secrets.
- `GET /api/satellite/observations` lists source-product metadata and state.
- `GET /api/satellite/channels` lists channels observed in the validated catalog.
- `GET /api/satellite/observations/{id}` returns the detailed provenance record.
- `GET /api/satellite/observations/{id}/image` serves a validated derived asset
  only when its state is `PROCESSED`.

`GET /api/satellite/layers` remains the NASA GIBS layer endpoint. It does not
claim that a GIBS overlay is INSAT imagery.
