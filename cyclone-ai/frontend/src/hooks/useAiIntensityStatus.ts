/** Read-only readiness state for the backend's Phase 5 intensity model. */
import { useCallback, useEffect, useState } from 'react';

import { fetchAiIntensityStatus } from '../services/api';
import type { AiIntensityStatus } from '../types/cyclone';

interface State {
  status: AiIntensityStatus | null;
  loading: boolean;
  error: string | null;
}

export function useAiIntensityStatus(): State {
  const [state, setState] = useState<State>({ status: null, loading: true, error: null });
  const load = useCallback(async () => {
    try {
      setState({ status: await fetchAiIntensityStatus(), loading: false, error: null });
    } catch (error) {
      setState({ status: null, loading: false, error: String(error) });
    }
  }, []);
  useEffect(() => {
    void load();
    const interval = window.setInterval(() => void load(), 60_000);
    return () => window.clearInterval(interval);
  }, [load]);
  return state;
}

