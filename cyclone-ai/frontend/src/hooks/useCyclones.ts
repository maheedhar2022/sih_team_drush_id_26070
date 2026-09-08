/**
 * CycloneAI — useCyclones hook
 *
 * Polls /api/cyclones/active every 30 seconds.
 * Returns list of active cyclones, loading state, and last update.
 */

import { useCallback, useEffect, useState } from 'react';
import { fetchActiveCyclones, fetchCycloneDetail, fetchCycloneTrack } from '../services/api';
import type { ActiveCyclonesResponse, Cyclone, CycloneDetail, CycloneTrack } from '../types/cyclone';

// ---- Active cyclones list -------------------------------------------------

interface CyclonesState {
  response: ActiveCyclonesResponse | null;
  cyclones: Cyclone[];
  loading: boolean;
  error: string | null;
  lastUpdatedUtc: string | null;
}

const POLL_INTERVAL_MS = 30_000;

export function useCyclones(): CyclonesState {
  const [state, setState] = useState<CyclonesState>({
    response: null,
    cyclones: [],
    loading: true,
    error: null,
    lastUpdatedUtc: null,
  });

  const fetch = useCallback(async () => {
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
    void fetch();
    const id = setInterval(() => void fetch(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetch]);

  return state;
}

// ---- Single cyclone detail + track ----------------------------------------

interface CycloneDetailState {
  detail: CycloneDetail | null;
  track: CycloneTrack | null;
  loading: boolean;
  error: string | null;
}

export function useCycloneDetail(cycloneId: string | null): CycloneDetailState {
  const [state, setState] = useState<CycloneDetailState>({
    detail: null,
    track: null,
    loading: false,
    error: null,
  });

  useEffect(() => {
    if (!cycloneId) {
      setState({ detail: null, track: null, loading: false, error: null });
      return;
    }

    let cancelled = false;

    const load = async () => {
      setState(prev => ({ ...prev, loading: true, error: null }));
      try {
        const [detail, track] = await Promise.all([
          fetchCycloneDetail(cycloneId),
          fetchCycloneTrack(cycloneId),
        ]);
        if (!cancelled) {
          setState({ detail, track, loading: false, error: null });
        }
      } catch (err) {
        if (!cancelled) {
          setState({ detail: null, track: null, loading: false, error: String(err) });
        }
      }
    };

    void load();
    return () => { cancelled = true; };
  }, [cycloneId]);

  return state;
}
