/**
 * CycloneAI — Root Application (Phase 2)
 *
 * Light Theme 2-Column Layout:
 * [ Sidebar (260px) | Map Area (flex-1, containing TopBar) ]
 *
 * Phase 2 changes:
 *  - Passes data_freshness from ActiveCyclonesResponse to TopBar + CycloneMap
 *  - Passes forecastTrack to CycloneMap
 *  - Passes dataSource string to CycloneMap badge
 */
import React, { useState } from 'react';
import { Sidebar }           from './components/Sidebar/Sidebar';
import { TopBar }            from './components/TopBar/TopBar';
import { CycloneMap }        from './components/Map/CycloneMap';
import { useCyclones, useCycloneDetail } from './hooks/useCyclones';
import { useSystemStatus } from './hooks/useSystemStatus';

const App: React.FC = () => {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { health }                          = useSystemStatus();
  const { cyclones, loading, error: cyErr, response } = useCyclones();
  const { detail, track, forecastTrack }    = useCycloneDetail(selectedId);

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
        />
      </div>
    </div>
  );
};

export default App;
