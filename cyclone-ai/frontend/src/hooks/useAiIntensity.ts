/**
 * Phase 5 — AI intensity inference hook.
 *
 * Accepts a File object selected by the user. Converts it to Uint8Array and
 * posts to POST /api/ai/intensity. Returns the typed result including all
 * model states: success, MODEL_NOT_TRAINED, INFERENCE_ERROR, etc.
 *
 * Never fabricates predictions. When no model is trained, the hook surfaces
 * the MODEL_NOT_TRAINED status from the backend verbatim.
 */
import { useCallback, useState } from 'react';

import { ApiError, fetchAiIntensity } from '../services/api';
import type { AiIntensityResult } from '../types/cyclone';

export type IntensityInferenceState =
  | { phase: 'idle' }
  | { phase: 'loading' }
  | { phase: 'success'; result: AiIntensityResult }
  | { phase: 'error'; message: string };

export function useAiIntensity() {
  const [state, setState] = useState<IntensityInferenceState>({ phase: 'idle' });

  const run = useCallback(async (file: File, source: string = 'user_upload') => {
    setState({ phase: 'loading' });
    try {
      const buffer = await file.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      const result = await fetchAiIntensity(bytes, file.type, source);
      setState({ phase: 'success', result });
    } catch (err) {
      const message =
        err instanceof ApiError
          ? `API error ${err.status}: ${err.detail}`
          : String(err);
      setState({ phase: 'error', message });
    }
  }, []);

  const reset = useCallback(() => setState({ phase: 'idle' }), []);

  return { state, run, reset };
}
