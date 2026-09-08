/**
 * CycloneAI — TypeScript Type Definitions
 *
 * Mirrors the Pydantic schemas in backend/app/schemas/cyclone.py
 */

// ---- Enums ----------------------------------------------------------------

export type DataMode = 'LIVE' | 'DEMO' | 'DELAYED' | 'OFFLINE';

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

// ---- Core -----------------------------------------------------------------

export interface TrackPoint {
  timestamp: string;          // ISO 8601
  latitude: number;
  longitude: number;
  wind_speed_kmh: number | null;
  pressure_hpa: number | null;
  intensity: IntensityCategory | null;
  source: string;
}

export interface Cyclone {
  id: string;
  name: string;
  basin: Basin;
  status: CycloneStatus;
  data_mode: DataMode;

  latitude: number;
  longitude: number;
  wind_speed_kmh: number | null;
  pressure_hpa: number | null;
  intensity: IntensityCategory | null;
  movement_direction: string | null;
  movement_speed_kmh: number | null;

  last_observation_utc: string;
  source: string;
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

// ---- API Responses --------------------------------------------------------

export interface ActiveCyclonesResponse {
  data_mode: DataMode;
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
}

// ---- UI State -------------------------------------------------------------

export interface SelectedCycloneState {
  cyclone: CycloneDetail | null;
  track: CycloneTrack | null;
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
