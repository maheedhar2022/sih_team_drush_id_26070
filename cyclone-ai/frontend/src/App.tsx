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
import React, { useEffect, useRef, useState } from 'react';
import { Sidebar }           from './components/Sidebar/Sidebar';
import { TopBar }            from './components/TopBar/TopBar';
import { CycloneMap }        from './components/Map/CycloneMap';
import { useCyclones, useCycloneDetail } from './hooks/useCyclones';
import { useSystemStatus } from './hooks/useSystemStatus';
import { useSatelliteLayers } from './hooks/useSatelliteLayers';
import { useSatelliteCatalog } from './hooks/useSatelliteCatalog';
import { useAiDetectionStatus } from './hooks/useAiDetectionStatus';
import { AiAnalysisPanel } from './components/AiAnalysis/AiAnalysisPanel';

const App: React.FC = () => {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [aiLabOpen, setAiLabOpen] = useState(false);
  const selectedInitialSystem = useRef(false);

  const { health }                          = useSystemStatus();
  const { cyclones, loading, error: cyErr, response } = useCyclones();
  const { detail, track, forecastTrack }    = useCycloneDetail(selectedId);

  // Satellite imagery layers (Phase 2b)
  const {
    layers: satLayers,
    enabled: satEnabled,
    opacities: satOpacities,
    dateLabel: satDateLabel,
    loading: satLoading,
    error: satError,
    toggleLayer: satToggle,
    setOpacity: satSetOpacity,
  } = useSatelliteLayers(detail?.last_observation_utc ?? null);
  const satelliteCatalog = useSatelliteCatalog();
  const aiDetection = useAiDetectionStatus();

  useEffect(() => {
    if (!selectedInitialSystem.current && cyclones.length > 0) {
      setSelectedId(cyclones[0].id);
      selectedInitialSystem.current = true;
    }
  }, [cyclones]);

  const toggle  = (id: string) => setSelectedId(prev => prev === id ? null : id);
  const displayMode = response?.data_mode ?? health?.data_mode ?? 'OFFLINE';

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
        dataMode={displayMode}
        aiLabOpen={aiLabOpen}
        onToggleAiLab={() => setAiLabOpen(open => !open)}
      />

      <main className="app-workspace">
        <section className="map-stage map-only-stage">
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
            satelliteLayers={satLayers}
            satelliteEnabled={satEnabled}
            satelliteOpacities={satOpacities}
            satelliteDateLabel={satDateLabel}
            satelliteLoading={satLoading}
            satelliteError={satError}
            onToggleSatelliteLayer={satToggle}
            onSetSatelliteOpacity={satSetOpacity}
            latestSatelliteObservation={satelliteCatalog.latestObservation}
            satelliteCatalogLoading={satelliteCatalog.loading}
            satelliteCatalogError={satelliteCatalog.error}
          />
          <AiAnalysisPanel
            open={aiLabOpen}
            status={aiDetection.status}
            loading={aiDetection.loading}
            error={aiDetection.error}
            onClose={() => setAiLabOpen(false)}
          />
        </section>
      </main>
    </div>
  );
};

export default App;
