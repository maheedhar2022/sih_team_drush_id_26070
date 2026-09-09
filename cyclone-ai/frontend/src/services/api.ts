/**
 * CycloneAI — Typed API Client (Phase 2)
 *
 * All backend communication goes through this module.
 * Base URL is read from VITE_API_URL. Without one, requests stay same-origin,
 * which lets Vercel route /api calls to the serverless backend.
 *
 * New in Phase 2:
 *   fetchForecastTrack() — official RSMC forecast track
 *   fetchDataSources()   — data source registry
 */

import type {
  ActiveCyclonesResponse,
  CycloneDetail,
  CycloneTrack,
  DataSourcesResponse,
  ForecastTrack,
  HealthResponse,
  SatelliteLayersListResponse,
  SatelliteCatalogStatus,
  SatelliteObservationListResponse,
} from '../types/cyclone';

const BASE_URL = import.meta.env.VITE_API_URL ?? '';

// ---- Generic fetch helper -------------------------------------------------

export class ApiError extends Error {
  public readonly status: number;
  public readonly detail: string;

  constructor(
    status: number,
    detail: string,
  ) {
    super(`API Error ${status}: ${detail}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`;
  let response: Response;

  try {
    response = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
  } catch (err) {
    throw new ApiError(0, `Network error — backend may be unreachable: ${String(err)}`);
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body?.detail ?? detail;
    } catch {
      // ignore JSON parse errors
    }
    throw new ApiError(response.status, detail);
  }

  return response.json() as Promise<T>;
}

// ---- API Methods ----------------------------------------------------------

/** Check backend health / status */
export async function fetchHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>('/api/health');
}

/** Fetch all active (or historical) cyclone systems */
export async function fetchActiveCyclones(): Promise<ActiveCyclonesResponse> {
  return apiFetch<ActiveCyclonesResponse>('/api/cyclones/active');
}

/** Fetch detailed info for a single cyclone */
export async function fetchCycloneDetail(id: string): Promise<CycloneDetail> {
  return apiFetch<CycloneDetail>(`/api/cyclones/${encodeURIComponent(id)}`);
}

/** Fetch the observed track for a cyclone */
export async function fetchCycloneTrack(id: string): Promise<CycloneTrack> {
  return apiFetch<CycloneTrack>(`/api/cyclones/${encodeURIComponent(id)}/track`);
}

/**
 * Fetch the official forecast track from RSMC New Delhi.
 * Returns null if no forecast is available (404 is normal when no active storm).
 */
export async function fetchForecastTrack(id: string): Promise<ForecastTrack | null> {
  try {
    return await apiFetch<ForecastTrack>(`/api/cyclones/${encodeURIComponent(id)}/forecast`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      return null; // no forecast available — expected and OK
    }
    throw err;
  }
}

/** Fetch the data source registry with provider statuses */
export async function fetchDataSources(): Promise<DataSourcesResponse> {
  return apiFetch<DataSourcesResponse>('/api/cyclones/sources/list');
}

/** Fetch available satellite imagery layers */
export async function fetchSatelliteLayers(date?: string): Promise<SatelliteLayersListResponse> {
  const params = date ? `?date=${date}` : '';
  return apiFetch<SatelliteLayersListResponse>(`/api/satellite/layers${params}`);
}

/** Read-only status for the MOSDAC/INSAT catalog. */
export async function fetchSatelliteCatalogStatus(): Promise<SatelliteCatalogStatus> {
  return apiFetch<SatelliteCatalogStatus>('/api/satellite/status');
}

/** Read-only, verified MOSDAC source-product records. */
export async function fetchSatelliteObservations(): Promise<SatelliteObservationListResponse> {
  return apiFetch<SatelliteObservationListResponse>('/api/satellite/observations?source=MOSDAC&limit=1');
}
