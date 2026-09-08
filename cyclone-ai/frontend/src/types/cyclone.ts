/**
 * CycloneAI — TypeScript Type Definitions (Phase 2)
 *
 * Mirrors the Pydantic schemas in backend/app/schemas/cyclone.py
 * New in Phase 2: DataFreshness, ForecastPoint, ForecastTrack,
 *                 DataSourceInfo, SatelliteLayerSpec
 */

// ---- Enums ----------------------------------------------------------------

export type DataMode = 'LIVE' | 'DEMO' | 'DELAYED' | 'OFFLINE' | 'HISTORICAL';

/**
 * Freshness of an observation relative to current time.
 * LIVE     — data < 6h old
 * DELAYED  — data 6–24h old
 * STALE    — data > 24h old, < 1 year
 * HISTORICAL — data > 1 year old (or verified historical dataset)
 * DEMO     — hard-coded demo (not from a real fetch)
 */
export type DataFreshness = 'LIVE' | 'DELAYED' | 'STALE' | 'HISTORICAL' | 'DEMO';

export type CycloneStatus = 'ACTIVE' | 'INACTIVE' | 'DISSIPATED';

export type SystemStatus = 'ONLINE' | 'DEGRADED' | 'OFFLINE';

export type Basin = 'NI' | 'NA' | 'EP' | 'WP' | 'SP' | 'SI' | 'SA';

export type IntensityCategory =
  | 'Depression'
  | 'Deep Depression'
  | 'Cyclonic Storm'
  | 'Severe Cyclonic Storm'
  | 'Very Severe Cyclonic Storm'
  | 'Extremely Severe Cyclonic Storm'
  | 'Super Cyclonic Storm';

// ---- Core Track Points ----------------------------------------------------

export interface TrackPoint {
  timestamp: string;          // ISO 8601 UTC
  latitude: number;
  longitude: number;
  wind_speed_kmh: number | null;
  pressure_hpa: number | null;
  intensity: IntensityCategory | null;
  source: string;
  data_freshness: DataFreshness | null;
}

/** Official forecast track point (rendered as dashed line) */
export interface ForecastPoint {
  issued_at_utc: string;      // when this forecast was issued
  valid_at_utc: string;       // when this point is valid
  forecast_hour: number;      // +6, +12, +24, +48, +72, +96, +120
  latitude: number;
  longitude: number;
  wind_speed_kmh: number | null;
  pressure_hpa: number | null;
  intensity: IntensityCategory | null;
  source: string;
  source_url: string | null;
}

// ---- Cyclone Summary & Detail ---------------------------------------------

export interface Cyclone {
  id: string;
  name: string;
  basin: Basin;
  status: CycloneStatus;
  data_mode: DataMode;
  data_freshness: DataFreshness;

  latitude: number;
  longitude: number;
  wind_speed_kmh: number | null;
  pressure_hpa: number | null;
  intensity: IntensityCategory | null;
  movement_direction: string | null;
  movement_speed_kmh: number | null;

  last_observation_utc: string;
  received_at_utc: string | null;
  source: string;
  source_url: string | null;

  year: number;
  season: string;
}

export interface CycloneDetail extends Cyclone {
  description: string | null;
  peak_wind_kmh: number | null;
  peak_intensity: IntensityCategory | null;
  landfall_expected: boolean | null;
  affected_regions: string[];
}

export interface CycloneTrack {
  cyclone_id: string;
  cyclone_name: string;
  data_mode: DataMode;
  source: string;
  points: TrackPoint[];
}

/** Official forecast track — displayed as dashed line on map */
export interface ForecastTrack {
  cyclone_id: string;
  cyclone_name: string;
  issued_at_utc: string;
  source: string;
  source_url: string | null;
  points: ForecastPoint[];
}

// ---- Data Source Info -------------------------------------------------------

/**
 * Metadata about a data source — for the source transparency panel.
 */
export interface DataSourceInfo {
  name: string;
  display_name: string;
  url: string | null;
  auth_type: string;
  update_frequency: string | null;
  last_fetched_utc: string | null;
  last_status: string;        // 'ok' | 'error' | 'unavailable' | 'disabled'
  last_error: string | null;
  enabled: boolean;
}

export interface DataSourcesResponse {
  sources: DataSourceInfo[];
  retrieved_at_utc: string;
}

// ---- Satellite Layer Spec (Phase 2b stub) ----------------------------------

export interface SatelliteLayerSpec {
  id: string;
  name: string;
  channel: string | null;     // 'VIS' | 'IR' | 'WV'
  source: string | null;
  source_url: string | null;
  timestamp_utc: string | null;
  tile_url: string | null;
  bbox: { N: number; S: number; E: number; W: number } | null;
  opacity: number;
  available: boolean;
  unavailable_reason: string | null;
}

// ---- API Responses ---------------------------------------------------------

export interface ActiveCyclonesResponse {
  data_mode: DataMode;
  data_freshness: DataFreshness;
  count: number;
  cyclones: Cyclone[];
  retrieved_at_utc: string;
  source: string;
  note: string | null;
}

export interface HealthResponse {
  status: SystemStatus;
  version: string;
  demo_mode: boolean;
  data_mode: DataMode;
  device: string;
  timestamp_utc: string;
  uptime_seconds: number | null;
  sources: Record<string, string>;
  // Phase 2 additions
  provider_statuses: Record<string, string>;
  last_ingestion_utc: string | null;
  active_ni_storms: number;
}

// ---- UI State --------------------------------------------------------------

export interface SelectedCycloneState {
  cyclone: CycloneDetail | null;
  track: CycloneTrack | null;
  forecastTrack: ForecastTrack | null;
  loading: boolean;
  error: string | null;
}

export interface MapLayer {
  id: string;
  label: string;
  enabled: boolean;
  available: boolean;
  unavailableReason?: string;
}
