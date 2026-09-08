/**
 * CycloneAI — Root Application (Phase 2b)
 *
 * Light Theme 2-Column Layout:
 * [ Sidebar (260px) | Map Area (flex-1, containing TopBar) ]
 *
 * Phase 2b changes:
 *  - Integrates useSatelliteLayers hook
 *  - Passes satellite layer state to CycloneMap
 *  - Layer toggle + opacity callbacks wired through
 */
import React, { useState } from 'react';
import { Sidebar }           from './components/Sidebar/Sidebar';
import { TopBar }            from './components/TopBar/TopBar';
import { CycloneMap }        from './components/Map/CycloneMap';
import { useCyclones, useCycloneDetail } from './hooks/useCyclones';
import { useSystemStatus } from './hooks/useSystemStatus';
import { useSatelliteLayers } from './hooks/useSatelliteLayers';

const App: React.FC = () => {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { health }                          = useSystemStatus();
  const { cyclones, loading, error: cyErr, response } = useCyclones();
  const { detail, track, forecastTrack }    = useCycloneDetail(selectedId);

  // Satellite imagery layers (Phase 2b)
  const {
    layers: satLayers,
    enabled: satEnabled,
    opacities: satOpacities,
    dateLabel: satDateLabel,
    toggleLayer: satToggle,
    setOpacity: satSetOpacity,
  } = useSatelliteLayers();

  const toggle  = (id: string) => setSelectedId(prev => prev === id ? null : id);
  const isDemo  = health?.demo_mode ?? true;

  // Data freshness from the active cyclones response
  const dataFreshness = response?.data_freshness ?? null;
  const dataSource    = response?.source ?? null;

  return (
    <div style={{
      width: '100vw', height: '100vh',
      display: 'flex',
      background: '#F9FAFB',
      fontFamily: "'Inter', system-ui, sans-serif",
      overflow: 'hidden',
    }}>
      {/* Left Sidebar */}
      <Sidebar
        cyclones={cyclones}
        selectedId={selectedId}
        onSelect={toggle}
        loading={loading}
        error={cyErr}
        demoMode={isDemo}
      />

      {/* Main Map Area */}
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        <TopBar
          detail={detail}
          health={health}
          dataFreshness={detail?.data_freshness ?? dataFreshness}
        />

        <CycloneMap
          cyclones={cyclones}
          selectedId={selectedId}
          track={track}
          forecastTrack={forecastTrack}
          dataFreshness={dataFreshness}
          dataSource={dataSource}
          onSelectCyclone={toggle}
          // Satellite imagery (Phase 2b)
          satelliteLayers={satLayers}
          satelliteEnabled={satEnabled}
          satelliteOpacities={satOpacities}
          satelliteDateLabel={satDateLabel}
          onToggleSatelliteLayer={satToggle}
          onSetSatelliteOpacity={satSetOpacity}
        />
      </div>
    </div>
  );
};

export default App;
