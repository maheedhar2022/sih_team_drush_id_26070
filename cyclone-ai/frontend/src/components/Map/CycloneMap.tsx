/**
 * CycloneAI — MapLibre GL Map (Light Theme)
 *
 * Features:
 *  - OSM base map (light, desaturated)
 *  - Historical track: solid dark line + dots
 *  - Compact map legend (OBSERVED / FORECAST / AI PREDICTION)
 *  - Layer control panel (architecture only — no fake satellite data)
 *  - DEMO / HISTORICAL MODE badge
 *
 * Layer Control Status:
 *  - Base Map (OSM): ✅ active
 *  - Satellite Imagery: ⏳ not yet available
 *  - Infrared (IR): ⏳ not yet available
 *  - Water Vapor (WV): ⏳ not yet available
 *  AI overlay: ⏳ Phase 2
 *
 * NOTE: No fake satellite imagery. No fake AI predictions.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import type { StyleSpecification } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

import type { Cyclone, CycloneTrack, DataFreshness, ForecastTrack } from '../../types/cyclone';

// ---- Map style: OSM Light -------------------------------------------------
const MAP_STYLE: StyleSpecification = {
  version: 8,
  glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors',
      maxzoom: 19,
    },
  },
  layers: [
    { id: 'bg',        type: 'background', paint: { 'background-color': '#F3F4F6' } },
    { id: 'osm-layer', type: 'raster',     source: 'osm', paint: { 'raster-opacity': 1, 'raster-saturation': -0.5 } },
  ],
};

// ---- Layer control state type ---------------------------------------------
interface LayerDef {
  id: string;
  label: string;
  sublabel: string;
  available: boolean;
  unavailableReason?: string;
  opacity: number;          // 0–100, future use
  source?: string;
  timestampNote?: string;
}

const LAYER_DEFS: LayerDef[] = [
  {
    id: 'osm',
    label: 'Base Map',
    sublabel: 'OpenStreetMap',
    available: true,
    opacity: 100,
    source: 'OpenStreetMap contributors',
  },
  {
    id: 'satellite',
    label: 'Satellite',
    sublabel: 'Visible imagery',
    available: false,
    unavailableReason: 'Satellite layer — Phase 2',
    opacity: 80,
    source: 'Pending: ISRO / NASA MODIS',
    timestampNote: 'Near-real-time (~2h delay)',
  },
  {
    id: 'infrared',
    label: 'Infrared (IR)',
    sublabel: 'Cloud-top temperature',
    available: false,
    unavailableReason: 'IR layer — Phase 2',
    opacity: 70,
    source: 'Pending: INSAT-3DR',
    timestampNote: 'Half-hourly composite',
  },
  {
    id: 'water_vapor',
    label: 'Water Vapor',
    sublabel: '6.2 µm channel',
    available: false,
    unavailableReason: 'WV layer — Phase 2',
    opacity: 70,
    source: 'Pending: INSAT-3DR',
    timestampNote: 'Half-hourly composite',
  },
];

// ---- Marker ---------------------------------------------------------------
function makeMarkerEl(color: string, selected: boolean, label: string): HTMLDivElement {
  const el = document.createElement('div');
  el.style.cssText = `
    background: #FFFFFF;
    border: 1.5px solid ${selected ? '#111827' : '#E5E7EB'};
    border-radius: 20px;
    padding: 4px 8px;
    display: flex;
    align-items: center;
    gap: 5px;
    cursor: pointer;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
    font-family: 'Inter', sans-serif;
    transition: all 0.2s ease;
    transform: ${selected ? 'scale(1.1)' : 'scale(1)'};
    z-index: ${selected ? 10 : 1};
  `;

  // Icon — small SVG spiral indicator
  const icon = document.createElement('div');
  icon.style.cssText = `
    width: 16px; height: 16px;
    background: ${color}22;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
  `;
  icon.innerHTML = `<svg viewBox="0 0 24 24" width="10" height="10" stroke="${color}" stroke-width="2.5" fill="none"><circle cx="12" cy="12" r="3"/><path d="M12 2a10 10 0 1 0 0 20"/></svg>`;

  const text = document.createElement('div');
  text.style.cssText = `font-size: 11px; font-weight: 600; color: #111827;`;
  text.innerText = label;

  el.appendChild(icon);
  el.appendChild(text);
  return el;
}

function markerColor(cat: string | null | undefined): string {
  if (!cat) return '#6B7280';
  if (cat.includes('Super'))       return '#DC2626';
  if (cat.includes('Extremely'))   return '#EF4444';
  if (cat.includes('Very Severe')) return '#F97316';
  if (cat.includes('Severe'))      return '#F59E0B';
  return '#3B82F6';
}

// ---- Component ------------------------------------------------------------
interface Props {
  cyclones: Cyclone[];
  selectedId: string | null;
  track: CycloneTrack | null;
  forecastTrack: ForecastTrack | null;
  dataFreshness?: DataFreshness | null;
  dataSource?: string | null;
  onSelectCyclone: (id: string) => void;
}

export const CycloneMap: React.FC<Props> = ({ cyclones, selectedId, track, forecastTrack, dataFreshness, dataSource, onSelectCyclone }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef       = useRef<maplibregl.Map | null>(null);
  const markerMap    = useRef<Map<string, maplibregl.Marker>>(new Map());
  const [loaded, setLoaded]             = useState(false);
  const [layerPanelOpen, setLayerPanelOpen] = useState(false);

  // Init map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const m = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: [88.0, 14.0],
      zoom: 4.0,
      attributionControl: false,
    });
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), 'bottom-right');
    m.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
    m.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
    m.on('load', () => setLoaded(true));
    mapRef.current = m;
    return () => { m.remove(); mapRef.current = null; };
  }, []);

  // Draw observed track
  const drawTrack = useCallback(() => {
    const m = mapRef.current;
    if (!m || !loaded) return;
    ['cyclone-track-line', 'cyclone-track-dots', 'cyclone-track-peak'].forEach(id => {
      if (m.getLayer(id)) m.removeLayer(id);
    });
    ['cyclone-track', 'cyclone-track-pts', 'cyclone-track-peak-pt'].forEach(id => {
      if (m.getSource(id)) m.removeSource(id);
    });

    if (!track) return;
    const coords = track.points.map(p => [p.longitude, p.latitude]);
    if (coords.length < 2) return;

    // Track line
    m.addSource('cyclone-track', {
      type: 'geojson',
      data: { type: 'Feature', geometry: { type: 'LineString', coordinates: coords }, properties: {} },
    });
    m.addLayer({
      id: 'cyclone-track-line', type: 'line', source: 'cyclone-track',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#111827', 'line-width': 2.5, 'line-opacity': 0.85 },
    });

    // Track dots (all points)
    m.addSource('cyclone-track-pts', {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: track.points.map(p => ({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [p.longitude, p.latitude] },
          properties: { wind: p.wind_speed_kmh, pres: p.pressure_hpa },
        })),
      },
    });
    m.addLayer({
      id: 'cyclone-track-dots', type: 'circle', source: 'cyclone-track-pts',
      paint: {
        'circle-radius': 3.5,
        'circle-color': '#FFFFFF',
        'circle-stroke-width': 1.5,
        'circle-stroke-color': '#111827',
      },
    });

    // Highlight peak point (240 km/h / 920 hPa)
    const peakPt = track.points.find(p => p.wind_speed_kmh === 240 && p.pressure_hpa === 920);
    if (peakPt) {
      m.addSource('cyclone-track-peak-pt', {
        type: 'geojson',
        data: {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [peakPt.longitude, peakPt.latitude] },
          properties: {},
        },
      });
      m.addLayer({
        id: 'cyclone-track-peak', type: 'circle', source: 'cyclone-track-peak-pt',
        paint: {
          'circle-radius': 6,
          'circle-color': '#DC2626',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#FFFFFF',
        },
      });
    }
  }, [track, loaded]);

  // Draw official forecast track (dashed line)
  const drawForecastTrack = useCallback(() => {
    const m = mapRef.current;
    if (!m || !loaded) return;
    ['cyclone-forecast-line'].forEach(id => {
      if (m.getLayer(id)) m.removeLayer(id);
    });
    ['cyclone-forecast'].forEach(id => {
      if (m.getSource(id)) m.removeSource(id);
    });
    if (!forecastTrack || forecastTrack.points.length < 2) return;
    const coords = forecastTrack.points.map(p => [p.longitude, p.latitude]);
    m.addSource('cyclone-forecast', {
      type: 'geojson',
      data: { type: 'Feature', geometry: { type: 'LineString', coordinates: coords }, properties: {} },
    });
    m.addLayer({
      id: 'cyclone-forecast-line', type: 'line', source: 'cyclone-forecast',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': '#2563EB',
        'line-width': 2,
        'line-opacity': 0.75,
        'line-dasharray': [4, 3],
      },
    });
  }, [forecastTrack, loaded]);

  useEffect(() => { drawForecastTrack(); }, [drawForecastTrack]);

  // Markers
  useEffect(() => {
    const m = mapRef.current;
    if (!m || !loaded) return;
    markerMap.current.forEach((mk, id) => {
      if (!cyclones.find(c => c.id === id)) { mk.remove(); markerMap.current.delete(id); }
    });
    cyclones.forEach(c => {
      const sel   = c.id === selectedId;
      const color = markerColor(c.intensity);
      const el    = makeMarkerEl(color, sel, c.name);
      el.addEventListener('click', (e) => { e.stopPropagation(); onSelectCyclone(c.id); });

      const popup = new maplibregl.Popup({
        closeButton: false, closeOnClick: false, offset: 12,
      }).setHTML(`
        <div style="font-size:12px;font-weight:600;color:#111827;">${c.name}</div>
        ${c.intensity ? `<div style="font-size:10px;color:${color};margin-top:2px;">${c.intensity}</div>` : ''}
        <div style="font-size:10px;color:#6B7280;margin-top:2px;">${c.wind_speed_kmh ?? '--'} km/h · ${c.pressure_hpa ?? '--'} hPa</div>
      `);
      el.addEventListener('mouseenter', () => popup.addTo(m));
      el.addEventListener('mouseleave', () => popup.remove());

      const existing = markerMap.current.get(c.id);
      if (existing) {
        existing.setLngLat([c.longitude, c.latitude]);
        existing.getElement().replaceWith(el);
      } else {
        const mk = new maplibregl.Marker({ element: el, anchor: 'center' })
          .setLngLat([c.longitude, c.latitude])
          .addTo(m);
        markerMap.current.set(c.id, mk);
      }
    });
  }, [cyclones, selectedId, loaded, onSelectCyclone]);

  // Fly to selected
  useEffect(() => {
    const m = mapRef.current;
    if (!m || !selectedId) return;
    const c = cyclones.find(x => x.id === selectedId);
    if (!c) return;
    m.flyTo({ center: [c.longitude, c.latitude], zoom: 5.2, duration: 1200 });
  }, [selectedId, cyclones]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      {/* Map canvas */}
      <div ref={containerRef} style={{ width: '100%', height: '100%', background: '#F3F4F6' }} />

      {/* ── DATA MODE badge — dynamic (LIVE / HISTORICAL / DEMO) ──────── */}
      <DataModeBadge freshness={dataFreshness ?? 'DEMO'} source={dataSource} />

      {/* ── MAP LEGEND ────────────────────────────────────────────────── */}
      <MapLegend />

      {/* ── LAYER CONTROL button ──────────────────────────────────────── */}
      <button
        id="map-layer-control-btn"
        onClick={() => setLayerPanelOpen(o => !o)}
        title="Map layer controls"
        style={{
          position: 'absolute', top: 12, right: 12, zIndex: 20,
          background: '#FFFFFF',
          border: '1px solid #E5E7EB',
          borderRadius: 8,
          padding: '7px 10px',
          cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 6,
          boxShadow: '0 2px 4px rgba(0,0,0,0.08)',
          fontSize: 12,
          fontWeight: 600,
          color: '#374151',
        }}
      >
        <LayerIcon />
        Layers
      </button>

      {/* ── LAYER CONTROL PANEL ───────────────────────────────────────── */}
      {layerPanelOpen && (
        <LayerPanel onClose={() => setLayerPanelOpen(false)} />
      )}
    </div>
  );
};

// ---- Map Legend -----------------------------------------------------------
function MapLegend() {
  return (
    <div style={{
      position: 'absolute', bottom: 56, right: 12, zIndex: 10,
      background: '#FFFFFF',
      border: '1px solid #E5E7EB',
      borderRadius: 8,
      padding: '10px 14px',
      boxShadow: '0 2px 4px rgba(0,0,0,0.06)',
      minWidth: 170,
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: '#9CA3AF', letterSpacing: '0.08em', marginBottom: 8 }}>
        LEGEND
      </div>

      <LegendRow
        swatch={<div style={{ width: 28, height: 2.5, background: '#111827', borderRadius: 1 }} />}
        label="Observed Track"
        sublabel="IMD/RSMC"
      />
      <LegendRow
        swatch={
          <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            {[0,1,2,3].map(i => (
              <div key={i} style={{ width: 5, height: 2, background: '#3B82F6', borderRadius: 1 }} />
            ))}
          </div>
        }
        label="Official Forecast"
        sublabel="Pending — Phase 2"
        unavailable
      />
      <LegendRow
        swatch={
          <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            {[0,1,2,3].map(i => (
              <div key={i} style={{ width: 5, height: 2, background: '#8B5CF6', borderRadius: 1, opacity: i % 2 === 0 ? 1 : 0.4 }} />
            ))}
          </div>
        }
        label="AI Prediction"
        sublabel="Pending — Phase 2"
        unavailable
      />
      <div style={{ marginTop: 8, borderTop: '1px solid #F3F4F6', paddingTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
        <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#DC2626', border: '2px solid #FFFFFF', boxShadow: '0 0 0 1px #DC2626' }} />
        <span style={{ fontSize: 11, color: '#374151' }}>Peak intensity</span>
      </div>
    </div>
  );
}

function LegendRow({ swatch, label, sublabel, unavailable }: {
  swatch: React.ReactNode;
  label: string;
  sublabel?: string;
  unavailable?: boolean;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 7, opacity: unavailable ? 0.45 : 1 }}>
      <div style={{ width: 30, display: 'flex', alignItems: 'center', justifyContent: 'flex-start' }}>
        {swatch}
      </div>
      <div>
        <div style={{ fontSize: 11, fontWeight: 600, color: '#374151' }}>{label}</div>
        {sublabel && <div style={{ fontSize: 10, color: '#9CA3AF' }}>{sublabel}</div>}
      </div>
    </div>
  );
}

// ---- Layer Control Panel --------------------------------------------------
function LayerPanel({ onClose }: { onClose: () => void }) {
  return (
    <div style={{
      position: 'absolute', top: 50, right: 12, zIndex: 30,
      background: '#FFFFFF',
      border: '1px solid #E5E7EB',
      borderRadius: 10,
      padding: '14px',
      boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
      minWidth: 240,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#111827', letterSpacing: '0.04em' }}>
          MAP LAYERS
        </span>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9CA3AF', fontSize: 16, lineHeight: 1, padding: 2 }}
        >
          ×
        </button>
      </div>

      {LAYER_DEFS.map(layer => (
        <LayerRow key={layer.id} layer={layer} />
      ))}

      <div style={{
        marginTop: 12, padding: '8px 10px',
        background: '#F9FAFB', borderRadius: 6,
        fontSize: 10, color: '#9CA3AF', lineHeight: 1.5,
      }}>
        <strong>Note:</strong> Satellite, IR, and WV layers require live data
        integration (Phase 2). No fabricated imagery is displayed.
      </div>
    </div>
  );
}

function LayerRow({ layer }: { layer: LayerDef }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      padding: '8px 0',
      borderBottom: '1px solid #F9FAFB',
      opacity: layer.available ? 1 : 0.5,
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{
            width: 12, height: 12, borderRadius: 3,
            background: layer.available ? '#10B981' : '#E5E7EB',
            border: `1px solid ${layer.available ? '#059669' : '#D1D5DB'}`,
            flexShrink: 0,
          }} />
          <span style={{ fontSize: 12, fontWeight: 600, color: '#111827' }}>{layer.label}</span>
          {!layer.available && (
            <span style={{ fontSize: 9, background: '#F3F4F6', color: '#9CA3AF', padding: '1px 5px', borderRadius: 3, fontWeight: 600 }}>
              PHASE 2
            </span>
          )}
        </div>
        <div style={{ fontSize: 10, color: '#6B7280', marginTop: 2, paddingLeft: 18 }}>{layer.sublabel}</div>
        {layer.source && (
          <div style={{ fontSize: 9, color: '#9CA3AF', marginTop: 1, paddingLeft: 18 }}>
            Src: {layer.source}
          </div>
        )}
        {layer.timestampNote && (
          <div style={{ fontSize: 9, color: '#9CA3AF', marginTop: 1, paddingLeft: 18 }}>
            {layer.timestampNote}
          </div>
        )}
      </div>
    </div>
  );
}

// ---- SVG Icon: layer stack ------------------------------------------------
function LayerIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 2 7 12 12 22 7 12 2"/>
      <polyline points="2 17 12 22 22 17"/>
      <polyline points="2 12 12 17 22 12"/>
    </svg>
  );
}

// ---- Data Mode Badge -------------------------------------------------------
const BADGE_STYLES: Record<string, { bg: string; color: string; border: string }> = {
  LIVE:       { bg: '#ECFDF5', color: '#065F46', border: '#6EE7B7' },
  DELAYED:    { bg: '#FFFBEB', color: '#92400E', border: '#FCD34D' },
  STALE:      { bg: '#FEF3C7', color: '#78350F', border: '#FDE68A' },
  HISTORICAL: { bg: '#F3F4F6', color: '#374151', border: '#D1D5DB' },
  DEMO:       { bg: '#EEF2FF', color: '#3730A3', border: '#C7D2FE' },
};

function DataModeBadge({ freshness, source }: { freshness: string; source?: string | null }) {
  const s = BADGE_STYLES[freshness] ?? BADGE_STYLES.DEMO;
  return (
    <div style={{
      position: 'absolute', bottom: 56, left: 12, zIndex: 10,
      background: s.bg,
      border: `1px solid ${s.border}`,
      color: s.color,
      borderRadius: 6,
      padding: '4px 10px',
      fontSize: 10,
      fontWeight: 700,
      letterSpacing: '0.06em',
      fontFamily: "'Roboto Mono', monospace",
      pointerEvents: 'none',
      userSelect: 'none',
      maxWidth: 300,
    }}>
      {freshness}
      {source && (
        <div style={{ fontWeight: 400, letterSpacing: 0, marginTop: 1, opacity: 0.8, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {source}
        </div>
      )}
    </div>
  );
}

