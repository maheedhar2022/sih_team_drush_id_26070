/**
 * CycloneAI — useSatelliteLayers hook (Phase 2b)
 *
 * Fetches available satellite imagery layers from /api/satellite/layers
 * and manages layer toggle + opacity state for the map.
 *
 * Returns:
 *   layers     — list of satellite layers with availability info
 *   loading    — true while fetching
 *   error      — error message if fetch failed
 *   enabled    — map of layer_id → boolean (is layer toggled on?)
 *   opacities  — map of layer_id → number (0–100)
 *   toggleLayer(id) — toggle a layer on/off
 *   setOpacity(id, value) — set a layer's opacity
 *   dateLabel  — human-readable date of the imagery
 */

import { useCallback, useEffect, useState } from 'react';
import { fetchSatelliteLayers } from '../services/api';
import type { SatelliteLayerSpec, SatelliteLayersListResponse } from '../types/cyclone';

interface SatelliteLayersState {
  layers: SatelliteLayerSpec[];
  loading: boolean;
  error: string | null;
  enabled: Record<string, boolean>;
  opacities: Record<string, number>;
  dateLabel: string | null;
  note: string | null;
}

export function useSatelliteLayers(observationTimestamp: string | null = null) {
  const [state, setState] = useState<SatelliteLayersState>({
    layers: [],
    loading: true,
    error: null,
    enabled: {},
    opacities: {},
    dateLabel: null,
    note: null,
  });

  useEffect(() => {
    let cancelled = false;

    // Never substitute today's imagery for a selected historical cyclone.
    if (!observationTimestamp) {
      setState({
        layers: [], loading: false, error: null, enabled: {}, opacities: {},
        dateLabel: null, note: null,
      });
      return () => { cancelled = true; };
    }

    const load = async () => {
      try {
        const observationDate = new Date(observationTimestamp);
        if (Number.isNaN(observationDate.getTime())) {
          throw new Error('Cyclone observation timestamp is invalid.');
        }
        const date = observationDate.toISOString().slice(0, 10);
        const response: SatelliteLayersListResponse = await fetchSatelliteLayers(date);
        if (cancelled) return;

        // Initialize opacities from defaults, enabled = false for all
        const opacities: Record<string, number> = {};
        const enabled: Record<string, boolean> = {};
        for (const layer of response.layers) {
          opacities[layer.layer_id] = Math.round(layer.default_opacity * 100);
          enabled[layer.layer_id] = false;
        }

        // Extract date label from first layer
        const dateLabel = response.layers[0]?.date_label ?? null;

        setState({
          layers: response.layers,
          loading: false,
          error: null,
          enabled,
          opacities,
          dateLabel,
          note: response.note,
        });
      } catch (err) {
        if (!cancelled) {
          setState(prev => ({
            ...prev,
            loading: false,
            error: String(err),
          }));
        }
      }
    };

    void load();
    return () => { cancelled = true; };
  }, [observationTimestamp]);

  const toggleLayer = useCallback((layerId: string) => {
    setState(prev => ({
      ...prev,
      enabled: {
        ...prev.enabled,
        [layerId]: !prev.enabled[layerId],
      },
    }));
  }, []);

  const setOpacity = useCallback((layerId: string, value: number) => {
    setState(prev => ({
      ...prev,
      opacities: {
        ...prev.opacities,
        [layerId]: value,
      },
    }));
  }, []);

  return {
    ...state,
    toggleLayer,
    setOpacity,
  };
}
