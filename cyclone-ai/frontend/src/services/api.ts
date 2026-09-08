/**
 * CycloneAI — Typed API Client
 *
 * All backend communication goes through this module.
 * Base URL is read from VITE_API_URL env var.
 */

import type {
  ActiveCyclonesResponse,
  CycloneDetail,
  CycloneTrack,
  HealthResponse,
} from '../types/cyclone';

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// ---- Generic fetch helper -------------------------------------------------

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`API Error ${status}: ${detail}`);
    this.name = 'ApiError';
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
    throw new ApiError(0, `Network error: ${String(err)}`);
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

/** Fetch all active (or demo) cyclone systems */
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

export { ApiError };
