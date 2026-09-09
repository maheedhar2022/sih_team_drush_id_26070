/**
 * CycloneAI — MapLibre GL Map (Phase 2b — Satellite Imagery)
 *
 * Features:
 *  - OSM base map (light, desaturated)
 *  - Historical track: solid dark line + dots
 *  - Forecast track: dashed blue line
 *  - ✅ Real satellite imagery layers (NASA GIBS WMTS)
 *  - Interactive layer panel with toggle + opacity sliders
 *  - Compact map legend
 *  - LIVE / HISTORICAL / DEMO mode badge
 *
 * Satellite Layer Support:
 *  - Visible (VIS): MODIS/VIIRS true-color reflectance
 *  - Infrared (IR): Cloud-top temperature
 *  - Water Vapor (WV): Mid-level humidity
 *  - Source: NASA GIBS (public, no auth required)
 *  - No fabricated imagery — real tiles with explicit timestamps
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import type { StyleSpecification } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

import type {
  Cyclone,
  CycloneTrack,
  DataFreshness,
  ForecastTrack,
  SatelliteCatalogStatus,
  SatelliteLayerSpec,
  SatelliteObservation,
} from '../../types/cyclone';

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

// ---- Channel icons --------------------------------------------------------
const CHANNEL_ICONS: Record<string, { color: string; emoji: string }> = {
  VIS:  { color: '#F59E0B', emoji: '☀' },
  IR:   { color: '#EF4444', emoji: '🌡' },
  WV:   { color: '#3B82F6', emoji: '💧' },
  TIR1: { color: '#EF4444', emoji: '🌡' },
};

// ---- Component ------------------------------------------------------------
interface Props {
  cyclones: Cyclone[];
  selectedId: string | null;
  track: CycloneTrack | null;
  forecastTrack: ForecastTrack | null;
  dataFreshness?: DataFreshness | null;
  dataSource?: string | null;
  onSelectCyclone: (id: string) => void;
  // Satellite layer props
  satelliteLayers?: SatelliteLayerSpec[];
  satelliteEnabled?: Record<string, boolean>;
  satelliteOpacities?: Record<string, number>;
  satelliteDateLabel?: string | null;
  satelliteLoading?: boolean;
  satelliteError?: string | null;
  onToggleSatelliteLayer?: (id: string) => void;
  onSetSatelliteOpacity?: (id: string, value: number) => void;
  satelliteCatalogStatus?: SatelliteCatalogStatus | null;
  latestSatelliteObservation?: SatelliteObservation | null;
  satelliteCatalogLoading?: boolean;
  satelliteCatalogError?: string | null;
}

export const CycloneMap: React.FC<Props> = ({
  cyclones, selectedId, track, forecastTrack,
  dataFreshness, dataSource, onSelectCyclone,
  satelliteLayers = [], satelliteEnabled = {},
  satelliteOpacities = {}, satelliteDateLabel, satelliteLoading = false, satelliteError = null,
  onToggleSatelliteLayer, onSetSatelliteOpacity,
  satelliteCatalogStatus = null, latestSatelliteObservation = null,
  satelliteCatalogLoading = false, satelliteCatalogError = null,
}) => {
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

  // ---- Satellite layers: add/remove raster sources dynamically ----
  useEffect(() => {
    const m = mapRef.current;
    if (!m || !loaded) return;

    for (const layer of satelliteLayers) {
      const srcId = `sat-src-${layer.layer_id}`;
      const lyrId = `sat-lyr-${layer.layer_id}`;
      const isOn = satelliteEnabled[layer.layer_id] && layer.available;
      const opacity = (satelliteOpacities[layer.layer_id] ?? 70) / 100;

      if (isOn) {
        // Add source + layer if not present
        if (!m.getSource(srcId)) {
          m.addSource(srcId, {
            type: 'raster',
            tiles: [layer.tile_url],
            tileSize: 256,
            attribution: layer.source,
            maxzoom: layer.max_zoom,
          });
        }
        if (!m.getLayer(lyrId)) {
          // Insert satellite layers below track lines (above base map)
          const beforeLayer = m.getLayer('cyclone-track-line') ? 'cyclone-track-line' : undefined;
          m.addLayer(
            {
              id: lyrId,
              type: 'raster',
              source: srcId,
              paint: { 'raster-opacity': opacity },
            },
            beforeLayer,
          );
        } else {
          // Update opacity if layer already exists
          m.setPaintProperty(lyrId, 'raster-opacity', opacity);
        }
      } else {
        // Remove layer + source if toggled off
        if (m.getLayer(lyrId)) m.removeLayer(lyrId);
        if (m.getSource(srcId)) m.removeSource(srcId);
      }
    }
  }, [satelliteLayers, satelliteEnabled, satelliteOpacities, loaded]);

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

  useEffect(() => { drawTrack(); }, [drawTrack]);
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

  // Count active satellite layers
  const activeSatCount = satelliteLayers.filter(l => satelliteEnabled[l.layer_id] && l.available).length;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      {/* Map canvas */}
      <div ref={containerRef} style={{ width: '100%', height: '100%', background: '#F3F4F6' }} />

      {/* ── DATA MODE badge — dynamic (LIVE / HISTORICAL / DEMO) ──────── */}
      <DataModeBadge freshness={dataFreshness ?? 'DEMO'} source={dataSource} />

      {/* ── MAP LEGEND ────────────────────────────────────────────────── */}
      <MapLegend activeSatCount={activeSatCount} satelliteDateLabel={satelliteDateLabel} />

      {/* ── LAYER CONTROL button ──────────────────────────────────────── */}
      <button
        id="map-layer-control-btn"
        onClick={() => setLayerPanelOpen(o => !o)}
        title="Map layer controls"
        style={{
          position: 'absolute', top: 12, right: 12, zIndex: 20,
          background: '#FFFFFF',
          border: `1px solid ${activeSatCount > 0 ? '#3B82F6' : '#E5E7EB'}`,
          borderRadius: 8,
          padding: '7px 10px',
          cursor: 'pointer',
          display: 'flex', alignItems: 'center', gap: 6,
          boxShadow: activeSatCount > 0
            ? '0 2px 8px rgba(59,130,246,0.2)'
            : '0 2px 4px rgba(0,0,0,0.08)',
          fontSize: 12,
          fontWeight: 600,
          color: activeSatCount > 0 ? '#2563EB' : '#374151',
          transition: 'all 0.2s ease',
        }}
      >
        <LayerIcon />
        Layers
        {activeSatCount > 0 && (
          <span style={{
            background: '#3B82F6', color: '#FFFFFF',
            borderRadius: 10, padding: '1px 6px',
            fontSize: 10, fontWeight: 700, minWidth: 16, textAlign: 'center',
          }}>
            {activeSatCount}
          </span>
        )}
      </button>

      {/* ── LAYER CONTROL PANEL ───────────────────────────────────────── */}
      {layerPanelOpen && (
        <LayerPanel
          onClose={() => setLayerPanelOpen(false)}
          satelliteLayers={satelliteLayers}
          satelliteEnabled={satelliteEnabled}
          satelliteOpacities={satelliteOpacities}
          satelliteDateLabel={satelliteDateLabel}
          satelliteLoading={satelliteLoading}
          satelliteError={satelliteError}
          onToggle={onToggleSatelliteLayer}
          onOpacity={onSetSatelliteOpacity}
          catalogStatus={satelliteCatalogStatus}
          latestObservation={latestSatelliteObservation}
          catalogLoading={satelliteCatalogLoading}
          catalogError={satelliteCatalogError}
        />
      )}
    </div>
  );
};

// ---- Map Legend -----------------------------------------------------------
function MapLegend({ activeSatCount, satelliteDateLabel }: {
  activeSatCount: number;
  satelliteDateLabel?: string | null;
}) {
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
        sublabel="RSMC New Delhi"
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
        sublabel="Pending — Phase 3"
        unavailable
      />

      {/* Satellite status indicator */}
      <div style={{ marginTop: 8, borderTop: '1px solid #F3F4F6', paddingTop: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <div style={{
            width: 10, height: 10, borderRadius: '50%',
            background: activeSatCount > 0 ? '#3B82F6' : '#E5E7EB',
            border: `2px solid ${activeSatCount > 0 ? '#DBEAFE' : '#F3F4F6'}`,
            transition: 'all 0.3s ease',
          }} />
          <span style={{ fontSize: 11, color: '#374151', fontWeight: 500 }}>
            Satellite {activeSatCount > 0 ? `(${activeSatCount} active)` : '(off)'}
          </span>
        </div>
        {activeSatCount > 0 && satelliteDateLabel && (
          <div style={{ fontSize: 10, color: '#6B7280', paddingLeft: 16 }}>
            Imagery: {satelliteDateLabel}
          </div>
        )}
      </div>

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
function LayerPanel({ onClose, satelliteLayers, satelliteEnabled, satelliteOpacities,
  satelliteDateLabel, satelliteLoading, satelliteError, onToggle, onOpacity,
  catalogStatus, latestObservation, catalogLoading, catalogError }: {
  onClose: () => void;
  satelliteLayers: SatelliteLayerSpec[];
  satelliteEnabled: Record<string, boolean>;
  satelliteOpacities: Record<string, number>;
  satelliteDateLabel?: string | null;
  satelliteLoading: boolean;
  satelliteError: string | null;
  onToggle?: (id: string) => void;
  onOpacity?: (id: string, value: number) => void;
  catalogStatus: SatelliteCatalogStatus | null;
  latestObservation: SatelliteObservation | null;
  catalogLoading: boolean;
  catalogError: string | null;
}) {
  return (
    <div style={{
      position: 'absolute', top: 50, right: 12, zIndex: 30,
      background: '#FFFFFF',
      border: '1px solid #E5E7EB',
      borderRadius: 10,
      padding: '14px',
      boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
      minWidth: 280,
      maxHeight: 'calc(100vh - 120px)',
      overflowY: 'auto',
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

      {/* Base map */}
      <LayerRowStatic
        label="Base Map"
        sublabel="OpenStreetMap"
        active={true}
        source="OpenStreetMap contributors"
      />

      {/* NASA GIBS layers header */}
      <div style={{
        fontSize: 10, fontWeight: 700, color: '#9CA3AF',
        letterSpacing: '0.08em', margin: '14px 0 8px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span>NASA GIBS IMAGERY</span>
        {satelliteDateLabel && (
          <span style={{
            background: '#EEF2FF', color: '#4338CA', padding: '2px 6px',
            borderRadius: 4, fontSize: 9, fontWeight: 600,
          }}>
            {satelliteDateLabel}
          </span>
        )}
      </div>

      {satelliteLoading && (
        <div style={{ fontSize: 11, color: '#9CA3AF', padding: '8px 0' }}>
          Loading satellite layers...
        </div>
      )}

      {!satelliteLoading && satelliteError && (
        <div style={{ fontSize: 11, color: '#B91C1C', padding: '8px 0', lineHeight: 1.45 }}>
          Satellite layer service is unavailable.
        </div>
      )}

      {!satelliteLoading && !satelliteError && satelliteLayers.length === 0 && (
        <div style={{ fontSize: 11, color: '#6B7280', padding: '8px 0', lineHeight: 1.45 }}>
          No source imagery is available for the selected date.
        </div>
      )}

      {/* GIBS layers (have tile_url) */}
      {satelliteLayers.filter(l => l.tile_url).map(layer => (
        <SatelliteLayerRow
          key={layer.layer_id}
          layer={layer}
          enabled={satelliteEnabled[layer.layer_id] ?? false}
          opacity={satelliteOpacities[layer.layer_id] ?? 70}
          onToggle={() => onToggle?.(layer.layer_id)}
          onOpacity={(v) => onOpacity?.(layer.layer_id, v)}
        />
      ))}

      {/* MOSDAC/ISRO layers (no tile_url — metadata only) */}
      {satelliteLayers.some(l => !l.tile_url) && (
        <>
          <div style={{
            fontSize: 10, fontWeight: 700, color: '#9CA3AF',
            letterSpacing: '0.08em', margin: '14px 0 8px',
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <span>MOSDAC / ISRO</span>
            <span style={{
              background: '#FFF7ED', color: '#C2410C', padding: '2px 6px',
              borderRadius: 4, fontSize: 9, fontWeight: 600,
            }}>
              INSAT-3DR
            </span>
          </div>

          {satelliteLayers.filter(l => !l.tile_url).map(layer => (
            <MOSDACLayerRow key={layer.layer_id} layer={layer} />
          ))}
        </>
      )}

      <CatalogSection
        status={catalogStatus}
        observation={latestObservation}
        loading={catalogLoading}
        error={catalogError}
      />

      <div style={{
        marginTop: 12, padding: '8px 10px',
        background: '#F9FAFB', borderRadius: 6,
        fontSize: 10, color: '#9CA3AF', lineHeight: 1.5,
      }}>
        <strong>Sources:</strong> NASA GIBS raster tiles. INSAT/MOSDAC products appear only after source-product validation.
      </div>
    </div>
  );
}

function CatalogSection({ status, observation, loading, error }: {
  status: SatelliteCatalogStatus | null;
  observation: SatelliteObservation | null;
  loading: boolean;
  error: string | null;
}) {
  const formatUtc = (value: string | null) => {
    if (!value) return 'No source product cataloged yet';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toISOString().replace('T', ' ').replace('.000Z', ' UTC');
  };

  return (
    <section style={{ marginTop: 14, borderTop: '1px solid #E5E7EB', paddingTop: 12 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        fontSize: 10, fontWeight: 700, color: '#6B7280', letterSpacing: '0.08em',
      }}>
        <span>INSAT / MOSDAC CATALOG</span>
        <span style={{ color: status?.catalog_state === 'READY' ? '#047857' : '#6B7280' }}>
          {loading ? 'CHECKING' : status?.catalog_state ?? 'UNAVAILABLE'}
        </span>
      </div>
      {error && (
        <div style={{ fontSize: 11, color: '#B91C1C', marginTop: 8, lineHeight: 1.45 }}>
          INSAT catalog status could not be loaded.
        </div>
      )}
      {!loading && !error && observation && (
        <div style={{ marginTop: 8, fontSize: 11, color: '#374151', lineHeight: 1.5 }}>
          <div style={{ fontWeight: 600 }}>{observation.satellite} {observation.processing_level ?? ''}</div>
          <div>{observation.product_id}</div>
          <div style={{ color: '#6B7280', overflowWrap: 'anywhere' }}>{observation.source_filename ?? observation.source_record_id}</div>
          <div style={{ color: '#6B7280' }}>Observed: {formatUtc(observation.observation_timestamp_utc)}</div>
          <div style={{ color: '#6B7280' }}>State: {observation.status}</div>
        </div>
      )}
      {!loading && !error && !observation && (
        <div style={{ fontSize: 11, color: '#6B7280', marginTop: 8, lineHeight: 1.45 }}>
          No validated INSAT source product is cataloged yet.
        </div>
      )}
    </section>
  );
}

function LayerRowStatic({ label, sublabel, active, source }: {
  label: string; sublabel: string; active: boolean; source: string;
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      padding: '8px 0',
      borderBottom: '1px solid #F9FAFB',
    }}>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{
            width: 12, height: 12, borderRadius: 3,
            background: active ? '#10B981' : '#E5E7EB',
            border: `1px solid ${active ? '#059669' : '#D1D5DB'}`,
            flexShrink: 0,
          }} />
          <span style={{ fontSize: 12, fontWeight: 600, color: '#111827' }}>{label}</span>
        </div>
        <div style={{ fontSize: 10, color: '#6B7280', marginTop: 2, paddingLeft: 18 }}>{sublabel}</div>
        <div style={{ fontSize: 9, color: '#9CA3AF', marginTop: 1, paddingLeft: 18 }}>
          Src: {source}
        </div>
      </div>
    </div>
  );
}

function SatelliteLayerRow({ layer, enabled, opacity, onToggle, onOpacity }: {
  layer: SatelliteLayerSpec;
  enabled: boolean;
  opacity: number;
  onToggle: () => void;
  onOpacity: (v: number) => void;
}) {
  const channelInfo = CHANNEL_ICONS[layer.channel] ?? { color: '#6B7280', emoji: '🛰' };
  const isAvailable = layer.available;

  return (
    <div style={{
      padding: '10px 0',
      borderBottom: '1px solid #F9FAFB',
      opacity: isAvailable ? 1 : 0.45,
      transition: 'opacity 0.2s ease',
    }}>
      {/* Row header: toggle + name */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {/* Toggle switch */}
        <button
          onClick={isAvailable ? onToggle : undefined}
          disabled={!isAvailable}
          title={isAvailable ? (enabled ? 'Hide layer' : 'Show layer') : (layer.unavailable_reason ?? 'Unavailable')}
          style={{
            width: 34, height: 18, borderRadius: 10,
            border: 'none', cursor: isAvailable ? 'pointer' : 'not-allowed',
            background: enabled && isAvailable ? '#3B82F6' : '#E5E7EB',
            position: 'relative',
            transition: 'background 0.2s ease',
            flexShrink: 0,
          }}
        >
          <div style={{
            width: 14, height: 14, borderRadius: '50%',
            background: '#FFFFFF',
            boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
            position: 'absolute', top: 2,
            left: enabled && isAvailable ? 18 : 2,
            transition: 'left 0.2s ease',
          }} />
        </button>

        {/* Channel icon */}
        <span style={{ fontSize: 14 }}>{channelInfo.emoji}</span>

        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#111827' }}>
            {layer.display_name}
          </div>
          <div style={{ fontSize: 10, color: '#6B7280' }}>
            {layer.instrument}
          </div>
        </div>

        {/* Channel badge */}
        <span style={{
          fontSize: 9, fontWeight: 700,
          background: `${channelInfo.color}18`,
          color: channelInfo.color,
          padding: '2px 6px', borderRadius: 4,
        }}>
          {layer.channel}
        </span>
      </div>

      {/* Opacity slider — only shown when enabled */}
      {enabled && isAvailable && (
        <div style={{ marginTop: 6, paddingLeft: 42, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 10, color: '#9CA3AF', width: 42 }}>Opacity</span>
          <input
            type="range"
            min={0} max={100}
            value={opacity}
            onChange={(e) => onOpacity(Number(e.target.value))}
            style={{
              flex: 1, height: 4, cursor: 'pointer',
              accentColor: '#3B82F6',
            }}
          />
          <span style={{ fontSize: 10, color: '#6B7280', width: 30, textAlign: 'right' }}>
            {opacity}%
          </span>
        </div>
      )}

      {/* Unavailable reason */}
      {!isAvailable && layer.unavailable_reason && (
        <div style={{ marginTop: 4, paddingLeft: 42, fontSize: 10, color: '#EF4444' }}>
          {layer.unavailable_reason}
        </div>
      )}
    </div>
  );
}
// ---- MOSDAC Layer Row (metadata only, no tiles) ---------------------------
function MOSDACLayerRow({ layer }: { layer: SatelliteLayerSpec }) {
  const channelInfo = CHANNEL_ICONS[layer.channel] ?? { color: '#6B7280', emoji: '🛰' };
  const isAvailable = layer.available;

  return (
    <div style={{
      padding: '8px 0',
      borderBottom: '1px solid #F9FAFB',
      opacity: isAvailable ? 1 : 0.45,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {/* Status indicator */}
        <div style={{
          width: 10, height: 10, borderRadius: '50%',
          background: isAvailable ? '#10B981' : '#E5E7EB',
          border: `2px solid ${isAvailable ? '#D1FAE5' : '#F3F4F6'}`,
          flexShrink: 0,
        }} />

        <span style={{ fontSize: 14 }}>{channelInfo.emoji}</span>

        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#111827' }}>
            {layer.display_name}
          </div>
          <div style={{ fontSize: 10, color: '#6B7280' }}>
            {layer.description}
          </div>
        </div>

        {/* ISRO badge */}
        <span style={{
          fontSize: 8, fontWeight: 700,
          background: '#FFF7ED',
          color: '#C2410C',
          padding: '2px 5px', borderRadius: 3,
          letterSpacing: '0.05em',
        }}>
          ISRO
        </span>
      </div>

      {isAvailable && (
        <div style={{ marginTop: 4, paddingLeft: 26, fontSize: 10, color: '#10B981' }}>
          ✓ Data available on MOSDAC
        </div>
      )}

      {!isAvailable && layer.unavailable_reason && (
        <div style={{ marginTop: 4, paddingLeft: 26, fontSize: 10, color: '#9CA3AF' }}>
          {layer.unavailable_reason}
        </div>
      )}
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
