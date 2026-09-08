/**
 * CycloneAI — useCyclones hook (Phase 2)
 *
 * Polls /api/cyclones/active every 5 minutes (IBTrACS updates every 6h).
 * New in Phase 2:
 *   - Returns full ActiveCyclonesResponse including data_freshness
 *   - useCycloneDetail also fetches official forecast track
 *   - useDataSources fetches the source registry
 */

import { useCallback, useEffect, useState } from 'react';
import {
  fetchActiveCyclones,
  fetchCycloneDetail,
  fetchCycloneTrack,
  fetchForecastTrack,
  fetchDataSources,
} from '../services/api';
import type {
  ActiveCyclonesResponse,
  Cyclone,
  CycloneDetail,
  CycloneTrack,
  ForecastTrack,
  DataSourcesResponse,
} from '../types/cyclone';

// IBTrACS updates every 6h — polling every 5 min is reasonable
const POLL_INTERVAL_MS = 5 * 60 * 1_000;

// ---- Active cyclones list --------------------------------------------------

interface CyclonesState {
  response: ActiveCyclonesResponse | null;
  cyclones: Cyclone[];
  loading: boolean;
  error: string | null;
  lastUpdatedUtc: string | null;
}

export function useCyclones(): CyclonesState {
  const [state, setState] = useState<CyclonesState>({
    response: null,
    cyclones: [],
    loading: true,
    error: null,
    lastUpdatedUtc: null,
  });

  const doFetch = useCallback(async () => {
    try {
      const response = await fetchActiveCyclones();
      setState({
        response,
        cyclones: response.cyclones,
        loading: false,
        error: null,
        lastUpdatedUtc: new Date().toISOString(),
      });
    } catch (err) {
      setState(prev => ({
        ...prev,
        loading: false,
        error: String(err),
        lastUpdatedUtc: new Date().toISOString(),
      }));
    }
  }, []);

  useEffect(() => {
    void doFetch();
    const id = setInterval(() => void doFetch(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [doFetch]);

  return state;
}

// ---- Single cyclone detail + observed track + forecast track ---------------

interface CycloneDetailState {
  detail: CycloneDetail | null;
  track: CycloneTrack | null;
  forecastTrack: ForecastTrack | null;
  loading: boolean;
  error: string | null;
}

export function useCycloneDetail(cycloneId: string | null): CycloneDetailState {
  const [state, setState] = useState<CycloneDetailState>({
    detail: null,
    track: null,
    forecastTrack: null,
    loading: false,
    error: null,
  });

  useEffect(() => {
    if (!cycloneId) {
      setState({ detail: null, track: null, forecastTrack: null, loading: false, error: null });
      return;
    }

    let cancelled = false;

    const load = async () => {
      setState(prev => ({ ...prev, loading: true, error: null }));
      try {
        const [detail, track, forecastTrack] = await Promise.all([
          fetchCycloneDetail(cycloneId),
          fetchCycloneTrack(cycloneId),
          fetchForecastTrack(cycloneId), // returns null if 404 — not an error
        ]);
        if (!cancelled) {
          setState({ detail, track, forecastTrack, loading: false, error: null });
        }
      } catch (err) {
        if (!cancelled) {
          setState({
            detail: null,
            track: null,
            forecastTrack: null,
            loading: false,
            error: String(err),
          });
        }
      }
    };

    void load();
    return () => { cancelled = true; };
  }, [cycloneId]);

  return state;
}

// ---- Data sources registry ------------------------------------------------

interface DataSourcesState {
  response: DataSourcesResponse | null;
  loading: boolean;
  error: string | null;
}

export function useDataSources(): DataSourcesState {
  const [state, setState] = useState<DataSourcesState>({
    response: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await fetchDataSources();
        if (!cancelled) setState({ response, loading: false, error: null });
      } catch (err) {
        if (!cancelled) setState({ response: null, loading: false, error: String(err) });
      }
    };
    void load();
    return () => { cancelled = true; };
  }, []);

  return state;
}
