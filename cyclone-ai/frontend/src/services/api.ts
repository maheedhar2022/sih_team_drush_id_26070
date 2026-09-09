/**
 * CycloneAI — Typed API Client (Phase 5)
 *
 * All backend communication goes through this module.
 * Base URL is read from VITE_API_URL. Without one, requests stay same-origin,
 * which lets Vercel route /api calls to the serverless backend.
 *
 * New in Phase 5:
 *   fetchAiIntensity() — real model inference (POST /api/ai/intensity)
 */

import type {
  ActiveCyclonesResponse,
  AiDetectionStatus,
  AiIntensityResult,
  AiIntensityStatus,
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

/** Read model readiness. This endpoint never creates a prediction. */
export async function fetchAiDetectionStatus(): Promise<AiDetectionStatus> {
  return apiFetch<AiDetectionStatus>('/api/ai/detection/status');
}

/** Read model and dataset readiness for Phase 5 intensity analysis. */
export async function fetchAiIntensityStatus(): Promise<AiIntensityStatus> {
  return apiFetch<AiIntensityStatus>('/api/ai/intensity/status');
}

/**
 * Submit raw image bytes to the Phase 5 intensity model.
 *
 * The backend returns MODEL_NOT_TRAINED (503) when no checkpoint exists.
 * This function does NOT throw on 503 — it returns the typed payload so the
 * UI can display the correct model-unavailable state.
 */
export async function fetchAiIntensity(
  imageBytes: ArrayBuffer,
  contentType: string,
  source: string,
  observationId?: string,
): Promise<AiIntensityResult> {
  const params = new URLSearchParams({ source });
  if (observationId) params.set('observation_id', observationId);
  const url = `${BASE_URL}/api/ai/intensity?${params}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': contentType },
      body: imageBytes,
    });
  } catch (err) {
    throw new ApiError(0, `Network error — backend may be unreachable: ${String(err)}`);
  }

  // 503 means MODEL_NOT_TRAINED or DEPENDENCY_UNAVAILABLE — return payload, not throw
  if (response.status === 503 || response.ok) {
    try {
      return (await response.json()) as AiIntensityResult;
    } catch {
      throw new ApiError(response.status, 'Intensity API returned non-JSON response');
    }
  }

  let detail = response.statusText;
  try {
    const body = await response.json();
    detail = body?.detail ?? detail;
  } catch {
    // ignore JSON parse errors
  }
  throw new ApiError(response.status, detail);
}
