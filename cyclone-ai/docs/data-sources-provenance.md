# Data Sources and Provenance

CycloneAI retains the source, source URL, source observation time, receipt time,
and processing time for every ingested observation. Observation time is never
substituted with the time a record was downloaded.

## Integrated Observed Tracks

### NOAA NCEI IBTrACS v04r01

- Role: primary observed North Indian Ocean cyclone track feed.
- Access: public CSV, no credentials.
- Data: storm ID, name, basin, timestamp, position, wind, pressure, intensity,
  and movement where reported.
- Processing: IMD/RSMC New Delhi fields are preferred when present; WMO values
  are an explicitly attributed fallback.
- Freshness: the service polls according to `IBTRACS_ACTIVE_REFRESH_HOURS`.
  The `LIVE`, `DELAYED`, `STALE`, and `HISTORICAL` labels are derived from the
  source observation timestamp, not client polling.
- Limitation: a successful poll does not imply a new upstream observation.

Official reference: <https://www.ncei.noaa.gov/products/international-best-track-archive>

## Official Forecast Architecture

### RSMC New Delhi / IMD bulletins

- Role: optional authoritative source for current observations and official
  forecast points during an active event.
- Access: public bulletin website; no credentials configured in the project.
- Enable with `RSMC_BULLETIN_ENABLED=true` only after validating the currently
  published bulletin format.
- Processing: forecast points are persisted separately in `cyclone_forecasts`
  and returned only from `GET /api/cyclones/{cyclone_id}/forecast`.
- Limitation: bulletin text is semi-structured and can change. The parser must
  fail closed: no parsed official forecast means the API returns `404`, never a
  fabricated track.

Official site: <https://rsmcnewdelhi.imd.gov.in>

## Satellite Metadata and Imagery

### NASA GIBS

- Role: public raster imagery layers used by the existing MapLibre map.
- Access: public WMTS tiles, no credentials.
- Data: availability-checked dated VIS, IR, and water-vapour-related layers.
- Limitation: products have source-specific latency and coverage. A returned
  tile URL is source imagery, not synthetic or modelled imagery.

### MOSDAC / ISRO

- Role: optional INSAT-3DR and INSAT-3DS imagery metadata and downloads.
- Access: official MOSDAC account credentials are required for authenticated
  downloads. Configure `MOSDAC_USERNAME` and `MOSDAC_PASSWORD` only in the
  backend environment, then set `MOSDAC_ENABLED=true` only after confirming
  the account and selected datasets work.
- Data: search metadata can be inspected before downloading; downloaded data
  products are not automatically treated as web map tiles.
- Limitation: a product is not made browseable until its source format,
  projection, channel metadata, and derived web asset have been validated.
  Credentials are never exposed to the frontend.

Official reference: <https://www.mosdac.gov.in/downloadapi-manual>

## Historical Mode

When no active North Indian Ocean system exists in the primary feed, CycloneAI
returns verified AMPHAN 2020 historical data from the backend. Responses are
marked `HISTORICAL` and name their IMD/RSMC and IBTrACS provenance. This mode is
for continuity of the map and API experience, not an indication of an active
event.
