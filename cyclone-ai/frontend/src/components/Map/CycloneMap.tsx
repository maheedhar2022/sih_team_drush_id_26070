/**
 * CycloneAI — MapLibre GL Map (Light Theme)
 * Light base map, minimal markers, dark track line.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import type { StyleSpecification } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

import type { Cyclone, CycloneTrack, MapLayer } from '../../types/cyclone';

// ---- Map style: Standard OSM (Light) ------------------------------------
const MAP_STYLE: StyleSpecification = {
  version: 8,
  glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
  sources: {
    'osm': {
      type: 'raster',
      tiles: [
        'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      ],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors',
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: 'bg',
      type: 'background',
      paint: { 'background-color': '#F3F4F6' },
    },
    {
      id: 'osm-layer',
      type: 'raster',
      source: 'osm',
      paint: {
        'raster-opacity': 1,
        'raster-saturation': -0.5,
      },
    },
  ],
};

// ---- Marker (White Pill Style) --------------------------------------------
function makeMarkerEl(color: string, selected: boolean, iconStr: string): HTMLDivElement {
  const el = document.createElement('div');
  el.style.cssText = `
    background: #FFFFFF;
    border: 1.5px solid ${selected ? '#111827' : '#E5E7EB'};
    border-radius: 20px;
    padding: 4px 8px;
    display: flex;
    align-items: center;
    gap: 4px;
    cursor: pointer;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
    font-family: 'Inter', sans-serif;
    transition: all 0.2s ease;
    transform: ${selected ? 'scale(1.1)' : 'scale(1)'};
    z-index: ${selected ? 10 : 1};
  `;
  
  // Icon circle
  const icon = document.createElement('div');
  icon.style.cssText = `
    width: 16px; height: 16px;
    background: ${color}22;
    color: ${color};
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 10px;
  `;
  icon.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" stroke="currentColor" stroke-width="2" fill="none"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>`; // simple hurricane-ish icon
  
  // Text
  const text = document.createElement('div');
  text.style.cssText = `font-size: 11px; font-weight: 600; color: #111827;`;
  text.innerText = iconStr;

  el.appendChild(icon);
  el.appendChild(text);

  return el;
}

function markerColor(cat: string | null | undefined): string {
  if (!cat) return '#6B7280';
  if (cat.includes('Extremely') || cat.includes('Super')) return '#EF4444';
  if (cat.includes('Very Severe')) return '#F97316';
  if (cat.includes('Severe'))      return '#F59E0B';
  return '#3B82F6';
}

// ---- Component ------------------------------------------------------------
interface Props {
  cyclones: Cyclone[];
  selectedId: string | null;
  track: CycloneTrack | null;
  onSelectCyclone: (id: string) => void;
}

export const CycloneMap: React.FC<Props> = ({ cyclones, selectedId, track, onSelectCyclone }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef       = useRef<maplibregl.Map | null>(null);
  const markerMap    = useRef<Map<string, maplibregl.Marker>>(new Map());
  const [loaded, setLoaded] = useState(false);

  // Init map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const m = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: [80.0, 14.0],
      zoom: 4.2,
      attributionControl: false,
    });
    
    // Add controls in a group
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), 'bottom-right');
    m.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
    m.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
    
    m.on('load', () => setLoaded(true));
    mapRef.current = m;
    return () => { m.remove(); mapRef.current = null; };
  }, []);

  // Draw track (Black line)
  const drawTrack = useCallback(() => {
    const m = mapRef.current;
    if (!m || !loaded) return;
    ['cyclone-track-line', 'cyclone-track-dots'].forEach(id => { if (m.getLayer(id)) m.removeLayer(id); });
    ['cyclone-track', 'cyclone-track-pts'].forEach(id => { if (m.getSource(id)) m.removeSource(id); });

    if (!track) return;
    const coords = track.points.map(p => [p.longitude, p.latitude]);
    if (coords.length < 2) return;

    m.addSource('cyclone-track', {
      type: 'geojson',
      data: { type: 'Feature', geometry: { type: 'LineString', coordinates: coords }, properties: {} },
    });
    m.addLayer({
      id: 'cyclone-track-line', type: 'line', source: 'cyclone-track',
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#111827', 'line-width': 2.5, 'line-opacity': 0.8 },
    });

    m.addSource('cyclone-track-pts', {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: track.points.map(p => ({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [p.longitude, p.latitude] },
          properties: {},
        })),
      },
    });
    m.addLayer({
      id: 'cyclone-track-dots', type: 'circle', source: 'cyclone-track-pts',
      paint: { 'circle-radius': 3.5, 'circle-color': '#FFFFFF', 'circle-stroke-width': 1.5, 'circle-stroke-color': '#111827' },
    });
  }, [track, loaded]);

  useEffect(() => { drawTrack(); }, [drawTrack]);

  // Markers
  useEffect(() => {
    const m = mapRef.current;
    if (!m || !loaded) return;

    markerMap.current.forEach((mk, id) => {
      if (!cyclones.find(c => c.id === id)) {
        mk.remove(); markerMap.current.delete(id);
      }
    });

    cyclones.forEach(c => {
      const sel   = c.id === selectedId;
      const color = markerColor(c.intensity);
      const el    = makeMarkerEl(color, sel, c.name);
      
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        onSelectCyclone(c.id);
      });

      const popup = new maplibregl.Popup({
        closeButton: false, closeOnClick: false, offset: 12, className: 'cyclone-popup'
      }).setHTML(`
        <div style="font-size:12px;font-weight:600;color:#111827;">${c.name}</div>
        ${c.intensity ? `<div style="font-size:10px;color:${color};margin-top:2px;">${c.intensity}</div>` : ''}
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
    m.flyTo({ center: [c.longitude, c.latitude], zoom: 5.5, duration: 1200 });
  }, [selectedId, cyclones]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%', background: '#F3F4F6' }} />
    </div>
  );
};
