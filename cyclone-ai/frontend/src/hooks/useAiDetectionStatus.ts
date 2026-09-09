/** Read-only state for the backend's trained detection model. */
import { useCallback, useEffect, useState } from 'react';

import { fetchAiDetectionStatus } from '../services/api';
import type { AiDetectionStatus } from '../types/cyclone';

interface AiDetectionState {
  status: AiDetectionStatus | null;
  loading: boolean;
  error: string | null;
}

export function useAiDetectionStatus(): AiDetectionState {
  const [state, setState] = useState<AiDetectionState>({ status: null, loading: true, error: null });
  const load = useCallback(async () => {
    try {
      const status = await fetchAiDetectionStatus();
      setState({ status, loading: false, error: null });
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
