/**
 * CycloneAI — Root Application
 *
 * Light Theme 2-Column Layout:
 * [ Sidebar (260px) | Map Area (flex-1, containing TopBar) ]
 */
import React, { useState } from 'react';
import { Sidebar }           from './components/Sidebar/Sidebar';
import { TopBar }            from './components/TopBar/TopBar';
import { CycloneMap }        from './components/Map/CycloneMap';
import { useCyclones, useCycloneDetail } from './hooks/useCyclones';
import { useSystemStatus } from './hooks/useSystemStatus';

const App: React.FC = () => {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { health, error: healthErr } = useSystemStatus();
  const { cyclones, loading, error: cyErr } = useCyclones();
  const { detail, track } = useCycloneDetail(selectedId);

  const toggle = (id: string) => setSelectedId(prev => prev === id ? null : id);
  const isDemo = health?.demo_mode ?? true;

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
        <TopBar detail={detail} health={health} />
        
        <CycloneMap
          cyclones={cyclones}
          selectedId={selectedId}
          track={track}
          onSelectCyclone={toggle}
        />
      </div>
    </div>
  );
};

export default App;
