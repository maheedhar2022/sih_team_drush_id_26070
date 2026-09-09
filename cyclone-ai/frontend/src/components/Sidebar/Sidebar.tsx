/**
 * CycloneAI — Sidebar
 * Full-height light sidebar.
 * Icons: inline SVG only (no emoji).
 */
import React from 'react';
import type { Cyclone, DataMode } from '../../types/cyclone';

interface Props {
  cyclones: Cyclone[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  error: string | null;
  dataMode: DataMode | 'OFFLINE';
}

// ---- SVG Icon set (scientific / UI — no emoji) ----------------------------

const IconMonitor = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
    <line x1="8" y1="21" x2="16" y2="21"/>
    <line x1="12" y1="17" x2="12" y2="21"/>
  </svg>
);

const IconArchive = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>
  </svg>
);

const IconLab = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v11l-4 4h14l-4-4V3"/>
  </svg>
);

const IconInfo = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
  </svg>
);

// Spiral / cyclone icon using SVG path (no emoji)
const IconCyclone = () => (
  <svg viewBox="0 0 24 24" width="18" height="18" stroke="#FFFFFF" strokeWidth="1.8" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2a10 10 0 1 0 0 20"/>
    <path d="M12 8a4 4 0 1 0 0 8"/>
    <path d="M12 12h.01"/>
    {/* spiral arcs */}
    <path d="M12 4c4.4 0 8 3.6 8 8"/>
    <path d="M12 7c2.8 0 5 2.2 5 5"/>
  </svg>
);

// ---- Component ------------------------------------------------------------

export const Sidebar: React.FC<Props> = ({ cyclones, selectedId, onSelect, loading, error, dataMode }) => {
  const isHistorical = dataMode === 'HISTORICAL' || dataMode === 'DEMO';
  const isOffline = dataMode === 'OFFLINE';
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
          borderRadius: 8,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <IconCyclone />
        </div>
        <div style={{ fontSize: 18, fontWeight: 700, color: '#111827', letterSpacing: '-0.02em' }}>
          CycloneAI
        </div>
      </div>

      {/* Navigation Links */}
      <nav style={{ padding: '0 12px', display: 'flex', flexDirection: 'column', gap: 4 }}>
        <NavItem Icon={IconMonitor} label="Monitor" active />
        <NavItem Icon={IconArchive} label="Archive" />
        <NavItem Icon={IconLab} label="AI Lab" />
        <NavItem Icon={IconInfo} label="About" />
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

      {/* Mode indicator (bottom) */}
      <div style={{ padding: '20px' }}>
        <div style={{
          background: isHistorical ? '#FEF3C7' : isOffline ? '#FEE2E2' : '#ECFDF5',
          borderRadius: 12,
          padding: '16px',
        }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: isHistorical ? '#92400E' : isOffline ? '#991B1B' : '#065F46', marginBottom: 4 }}>
            {isHistorical ? 'Historical Data' : isOffline ? 'Data Service Offline' : 'Live Data'}
          </div>
          <div style={{ fontSize: 11, color: isHistorical ? '#B45309' : isOffline ? '#B91C1C' : '#047857', lineHeight: 1.4 }}>
            {isHistorical
              ? 'Verified AMPHAN 2020 historical record from IMD/RSMC.'
              : isOffline
                ? 'The dashboard will reconnect automatically when data is available.'
                : 'Monitoring current source observations. Follow official IMD warnings.'}
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

function NavItem({ Icon, label, active }: { Icon: React.FC; label: string; active?: boolean }) {
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
      <span style={{ display: 'flex', alignItems: 'center' }}><Icon /></span>
      <span>{label}</span>
    </button>
  );
}
