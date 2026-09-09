import { useCallback, useEffect, useState } from 'react';
import { fetchSatelliteCatalogStatus, fetchSatelliteObservations } from '../services/api';
import type { SatelliteCatalogStatus, SatelliteObservation } from '../types/cyclone';

const CATALOG_POLL_INTERVAL_MS = 5 * 60 * 1_000;

interface SatelliteCatalogState {
  status: SatelliteCatalogStatus | null;
  latestObservation: SatelliteObservation | null;
  loading: boolean;
  error: string | null;
}

export function useSatelliteCatalog(): SatelliteCatalogState {
  const [state, setState] = useState<SatelliteCatalogState>({
    status: null,
    latestObservation: null,
    loading: true,
    error: null,
  });

  const load = useCallback(async () => {
    try {
      const [status, observations] = await Promise.all([
        fetchSatelliteCatalogStatus(),
        fetchSatelliteObservations(),
      ]);
      setState({
        status,
        latestObservation: observations.observations[0] ?? null,
        loading: false,
        error: null,
      });
    } catch (error) {
      setState(previous => ({ ...previous, loading: false, error: String(error) }));
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => void load(), CATALOG_POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [load]);

  return state;
}
