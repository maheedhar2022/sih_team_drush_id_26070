/**
 * CycloneAI — useSystemStatus hook
 *
 * Polls /api/health every 60 seconds.
 * Returns system health state including demo_mode flag.
 */

import { useCallback, useEffect, useState } from 'react';
import { fetchHealth } from '../services/api';
import type { HealthResponse } from '../types/cyclone';

interface SystemStatusState {
  health: HealthResponse | null;
  loading: boolean;
  error: string | null;
  lastCheckedUtc: string | null;
}

const POLL_INTERVAL_MS = 60_000;

export function useSystemStatus(): SystemStatusState {
  const [state, setState] = useState<SystemStatusState>({
    health: null,
    loading: true,
    error: null,
    lastCheckedUtc: null,
  });

  const check = useCallback(async () => {
    try {
      const health = await fetchHealth();
      setState({
        health,
        loading: false,
        error: null,
        lastCheckedUtc: new Date().toISOString(),
      });
    } catch (err) {
      setState(prev => ({
        ...prev,
        loading: false,
        error: String(err),
        lastCheckedUtc: new Date().toISOString(),
      }));
    }
  }, []);

  useEffect(() => {
    void check();
    const id = setInterval(() => void check(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [check]);

  return state;
}
