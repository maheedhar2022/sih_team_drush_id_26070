/**
 * CycloneAI — Sidebar
 * Full-height light sidebar inspired by modern map apps.
 */
import React from 'react';
import type { Cyclone } from '../../types/cyclone';

interface Props {
  cyclones: Cyclone[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  error: string | null;
  demoMode: boolean;
}

export const Sidebar: React.FC<Props> = ({ cyclones, selectedId, onSelect, loading, error, demoMode }) => {
  return (
    <aside style={{
      width: 260,
      flexShrink: 0,
      background: '#FFFFFF',
      borderRight: '1px solid #E5E7EB',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
    }}>
      {/* Logo Area */}
      <div style={{ padding: '24px 20px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{
          width: 32, height: 32,
          background: '#111827',
          color: '#FFFFFF',
          borderRadius: 8,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 16,
        }}>🌀</div>
        <div style={{ fontSize: 18, fontWeight: 700, color: '#111827', letterSpacing: '-0.02em' }}>
          CycloneAI
        </div>
      </div>

      {/* Navigation Links */}
      <nav style={{ padding: '0 12px', display: 'flex', flexDirection: 'column', gap: 4 }}>
        <NavItem icon="📍" label="Monitor" active />
        <NavItem icon="🕰️" label="Archive" />
        <NavItem icon="🧪" label="AI Lab" />
        <NavItem icon="ℹ️" label="About" />
      </nav>

      {/* Divider */}
      <div style={{ margin: '24px 20px 12px', borderBottom: '1px solid #F3F4F6' }} />

      {/* Active Systems List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 12px' }}>
        <div style={{
          padding: '8px',
          fontSize: 12, fontWeight: 600, color: '#9CA3AF',
          display: 'flex', justifyContent: 'space-between'
        }}>
          <span>Active Systems</span>
          {!loading && <span style={{ background: '#F3F4F6', padding: '2px 6px', borderRadius: 10, color: '#4B5563', fontSize: 10 }}>{cyclones.length}</span>}
        </div>

        {loading && <div style={{ padding: '12px 8px', fontSize: 13, color: '#6B7280' }}>Loading systems...</div>}
        {error && <div style={{ padding: '12px 8px', fontSize: 13, color: '#EF4444' }}>{error}</div>}
        {!loading && !error && cyclones.length === 0 && (
          <div style={{ padding: '12px 8px', fontSize: 13, color: '#6B7280' }}>No active systems.</div>
        )}

        {!loading && !error && cyclones.map(c => {
          const sel = c.id === selectedId;
          return (
            <button
              key={c.id}
              onClick={() => onSelect(c.id)}
              style={{
                width: '100%', textAlign: 'left',
                background: sel ? '#F3F4F6' : 'transparent',
                border: 'none',
                borderRadius: 8,
                padding: '12px',
                cursor: 'pointer',
                marginBottom: 4,
                display: 'flex', flexDirection: 'column', gap: 4,
                transition: 'background 0.2s'
              }}
              onMouseEnter={(e) => { if (!sel) e.currentTarget.style.background = '#F9FAFB'; }}
              onMouseLeave={(e) => { if (!sel) e.currentTarget.style.background = 'transparent'; }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 14, fontWeight: 600, color: '#111827' }}>{c.name}</span>
                {c.data_mode === 'DEMO' && (
                  <span style={{ fontSize: 10, fontWeight: 600, color: '#B45309', background: '#FEF3C7', padding: '2px 6px', borderRadius: 4 }}>DEMO</span>
                )}
              </div>
              {c.intensity && (
                <div style={{ fontSize: 12, color: '#4B5563' }}>{c.intensity}</div>
              )}
            </button>
          );
        })}
      </div>

      {/* Promo/Disclaimer Area (Bottom) */}
      <div style={{ padding: '20px' }}>
        <div style={{
          background: demoMode ? '#FEF3C7' : '#F3F4F6',
          borderRadius: 12,
          padding: '16px',
        }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: demoMode ? '#92400E' : '#111827', marginBottom: 4 }}>
            {demoMode ? 'Historical Demo Mode' : 'Live Data Mode'}
          </div>
          <div style={{ fontSize: 11, color: demoMode ? '#B45309' : '#4B5563', lineHeight: 1.4 }}>
            {demoMode 
              ? 'Displaying 2020 Cyclone AMPHAN data for demonstration purposes.' 
              : 'AI analysis is experimental. Follow official IMD warnings.'}
          </div>
        </div>
        
        <div style={{ marginTop: 16, display: 'flex', gap: 12, fontSize: 11, color: '#9CA3AF' }}>
          <span>Terms</span>
          <span>Privacy</span>
          <span>Gov.in</span>
        </div>
      </div>
    </aside>
  );
};

function NavItem({ icon, label, active }: { icon: string; label: string; active?: boolean }) {
  return (
    <button style={{
      display: 'flex', alignItems: 'center', gap: 12,
      width: '100%',
      padding: '10px 12px',
      background: active ? '#F3F4F6' : 'transparent',
      border: 'none',
      borderRadius: 8,
      cursor: 'pointer',
      color: active ? '#111827' : '#4B5563',
      fontWeight: active ? 600 : 500,
      fontSize: 14,
    }}>
      <span style={{ fontSize: 18 }}>{icon}</span>
      <span>{label}</span>
    </button>
  );
}
