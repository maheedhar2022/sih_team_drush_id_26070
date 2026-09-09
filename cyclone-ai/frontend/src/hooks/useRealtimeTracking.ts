/**
 * CycloneAI — Real-Time Tracking Hook (Phase 5)
 *
 * Provides smooth, animated cyclone positions by:
 * 1. Polling /api/cyclones/live every 30s for latest positions
 * 2. Interpolating between the last two known positions for smooth movement
 * 3. Computing animated position using requestAnimationFrame
 *
 * Also attempts WebSocket connection for instant push updates.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

const POLL_INTERVAL_MS = 30_000;  // 30 seconds

// ---- Types ----------------------------------------------------------------

export interface LivePosition {
  cyclone_id: string;
  cyclone_name: string;
  latitude: number;
  longitude: number;
  wind_speed_kmh: number | null;
  pressure_hpa: number | null;
  intensity_category: string | null;
  timestamp_utc: string | null;
  basin: string;
}

export interface AnimatedPosition extends LivePosition {
  /** Interpolated latitude (smoothly animated) */
  animLat: number;
  /** Interpolated longitude (smoothly animated) */
  animLon: number;
  /** Animation progress 0-1 between last two positions */
  progress: number;
  /** Whether this marker is actively animating */
  isAnimating: boolean;
}

interface RealtimeState {
  positions: AnimatedPosition[];
  connected: boolean;
  lastUpdate: string | null;
  error: string | null;
}

// ---- Interpolation --------------------------------------------------------

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * Math.min(1, Math.max(0, t));
}

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

// ---- Hook -----------------------------------------------------------------

export function useRealtimeTracking(): RealtimeState {
  const [state, setState] = useState<RealtimeState>({
    positions: [],
    connected: false,
    lastUpdate: null,
    error: null,
  });

  // Store previous positions for interpolation
  const prevPositions = useRef<Map<string, LivePosition>>(new Map());
  const currentPositions = useRef<Map<string, LivePosition>>(new Map());
  const animationRef = useRef<number>(0);
  const transitionStart = useRef<number>(0);
  const TRANSITION_DURATION = 2000; // 2 seconds smooth transition

  // Fetch live positions
  const fetchPositions = useCallback(async () => {
    try {
      const BASE_URL = import.meta.env.VITE_API_URL ?? '';
      const response = await fetch(`${BASE_URL}/api/cyclones/live`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();

      // Shift current → previous
      prevPositions.current = new Map(currentPositions.current);

      // Update current
      const newMap = new Map<string, LivePosition>();
      for (const pos of data.positions) {
        newMap.set(pos.cyclone_id, pos);
      }
      currentPositions.current = newMap;
      transitionStart.current = performance.now();

      setState(prev => ({
        ...prev,
        connected: true,
        lastUpdate: data.server_time_utc,
        error: null,
      }));
    } catch (err) {
      setState(prev => ({
        ...prev,
        error: String(err),
      }));
    }
  }, []);

  // Animation loop
  useEffect(() => {
    let running = true;

    function animate() {
      if (!running) return;

      const now = performance.now();
      const elapsed = now - transitionStart.current;
      const rawProgress = Math.min(1, elapsed / TRANSITION_DURATION);
      const easedProgress = easeInOutCubic(rawProgress);

      const animated: AnimatedPosition[] = [];

      for (const [id, curr] of currentPositions.current) {
        const prev = prevPositions.current.get(id);

        if (prev && rawProgress < 1) {
          // Animate between previous and current position
          animated.push({
            ...curr,
            animLat: lerp(prev.latitude, curr.latitude, easedProgress),
            animLon: lerp(prev.longitude, curr.longitude, easedProgress),
            progress: easedProgress,
            isAnimating: true,
          });
        } else {
          // No previous position or animation complete
          animated.push({
            ...curr,
            animLat: curr.latitude,
            animLon: curr.longitude,
            progress: 1,
            isAnimating: false,
          });
        }
      }

      setState(prev => ({
        ...prev,
        positions: animated,
      }));

      animationRef.current = requestAnimationFrame(animate);
    }

    animationRef.current = requestAnimationFrame(animate);

    return () => {
      running = false;
      cancelAnimationFrame(animationRef.current);
    };
  }, []);

  // Polling
  useEffect(() => {
    void fetchPositions();
    const id = setInterval(() => void fetchPositions(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchPositions]);

  // WebSocket connection (optional enhancement)
  useEffect(() => {
    const BASE_URL = import.meta.env.VITE_API_URL ?? '';
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsBase = BASE_URL
      ? BASE_URL.replace(/^https?:/, wsProtocol)
      : `${wsProtocol}//${window.location.host}`;
    const wsUrl = `${wsBase}/api/ws/cyclones`;

    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      try {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          setState(prev => ({ ...prev, connected: true, error: null }));
        };

        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'initial' || msg.type === 'heartbeat' || msg.type === 'update') {
              const data = msg.data;
              // Shift current → previous
              prevPositions.current = new Map(currentPositions.current);
              const newMap = new Map<string, LivePosition>();
              for (const pos of data.positions) {
                newMap.set(pos.cyclone_id, pos);
              }
              currentPositions.current = newMap;
              transitionStart.current = performance.now();

              setState(prev => ({
                ...prev,
                connected: true,
                lastUpdate: data.server_time_utc,
              }));
            }
          } catch {
            // Ignore parse errors
          }
        };

        ws.onclose = () => {
          setState(prev => ({ ...prev, connected: false }));
          // Reconnect after 5s
          reconnectTimer = setTimeout(connect, 5000);
        };

        ws.onerror = () => {
          // WebSocket failed — polling is still active as fallback
          ws?.close();
        };
      } catch {
        // WebSocket not available — polling handles it
        reconnectTimer = setTimeout(connect, 10000);
      }
    }

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);

  return state;
}
