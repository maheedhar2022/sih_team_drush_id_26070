/**
 * CycloneAI — TopBar
 * Floating pill-shaped top bar showing selected cyclone details.
 * Icons: inline SVG only (no emoji).
 * Shows: name, wind, pressure, direction, observation timestamp, lat/lon.
 */
import React from 'react';
import type { CycloneDetail, DataFreshness, HealthResponse } from '../../types/cyclone';

interface Props {
  detail: CycloneDetail | null;
  health: HealthResponse | null;
  dataFreshness?: DataFreshness | null;
}

// ---- SVG Icon primitives (scientific, no emoji) ---------------------------

const IconWind = () => (
  <svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17.7 7.7a2.5 2.5 0 1 1 1.8 4.3H2"/>
    <path d="M9.6 4.6A2 2 0 1 1 11 8H2"/>
    <path d="M12.6 19.4A2 2 0 1 0 14 16H2"/>
  </svg>
);

const IconPressure = () => (
  <svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"/>
    <polyline points="12 6 12 12 16 14"/>
  </svg>
);

const IconDirection = () => (
  <svg viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="3 11 22 2 13 21 11 13 3 11"/>
  </svg>
);

const IconClock = () => (
  <svg viewBox="0 0 24 24" width="11" height="11" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"/>
    <polyline points="12 6 12 12 16 14"/>
  </svg>
);

const IconCoords = () => (
  <svg viewBox="0 0 24 24" width="11" height="11" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <line x1="12" y1="2" x2="12" y2="6"/>
    <line x1="12" y1="18" x2="12" y2="22"/>
    <line x1="2" y1="12" x2="6" y2="12"/>
    <line x1="18" y1="12" x2="22" y2="12"/>
  </svg>
);

// ---- Helpers ---------------------------------------------------------------

function formatObsTime(iso: string | null | undefined): string {
  if (!iso) return '--';
  try {
    const d = new Date(iso);
    return d.toISOString().replace('T', ' ').replace('.000Z', 'Z');
  } catch {
    return '--';
  }
}

function formatCoord(val: number | null | undefined, axis: 'lat' | 'lon'): string {
  if (val == null) return '--';
  const abs = Math.abs(val).toFixed(2);
  if (axis === 'lat') return `${abs}°${val >= 0 ? 'N' : 'S'}`;
  return `${abs}°${val >= 0 ? 'E' : 'W'}`;
}

// ---- Components ------------------------------------------------------------

export const TopBar: React.FC<Props> = ({ detail, health, dataFreshness }) => {
  if (!detail) {
    return (
      <div style={{
        position: 'absolute', top: 20, left: 20, zIndex: 10,
        background: '#FFFFFF',
        borderRadius: 24,
        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05)',
        padding: '12px 24px',
        display: 'flex', alignItems: 'center', gap: 12,
        border: '1px solid #E5E7EB',
      }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: '#111827' }}>Indian Ocean Region</span>
        <div style={{ width: 1, height: 16, background: '#E5E7EB' }} />
        <span style={{ fontSize: 13, color: '#6B7280' }}>Select a cyclone to view details</span>
        <div style={{ width: 1, height: 16, background: '#E5E7EB' }} />
        <StatusBadge online={health?.status === 'ONLINE'} />
      </div>
    );
  }

  return (
    <div style={{
      position: 'absolute', top: 20, left: 20, zIndex: 10,
      background: '#FFFFFF',
      borderRadius: 24,
      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 10px 15px -3px rgba(0, 0, 0, 0.1)',
      padding: '8px 12px 8px 24px',
      display: 'flex', alignItems: 'center', gap: 14,
      border: '1px solid #E5E7EB',
      flexWrap: 'wrap',
    }}>
      {/* Name + active dot */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>{detail.name}</span>
        {detail.status === 'ACTIVE' && (
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#EF4444', display: 'inline-block' }} />
        )}
      </div>

      <div style={{ width: 1, height: 20, background: '#E5E7EB' }} />

      {/* Meteorological chips */}
      <div style={{ display: 'flex', gap: 6 }}>
        <Chip Icon={IconWind}      label={`${detail.wind_speed_kmh ?? '--'} km/h`} />
        <Chip Icon={IconPressure}  label={`${detail.pressure_hpa ?? '--'} hPa`} />
        <Chip Icon={IconDirection} label={detail.movement_direction ?? '--'} />
      </div>

      <div style={{ width: 1, height: 20, background: '#E5E7EB' }} />

      {/* Observation metadata row */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <MetaRow Icon={IconClock} label={`Obs: ${formatObsTime(detail.last_observation_utc)}`} />
        {detail.received_at_utc && (
          <MetaRow Icon={IconClock} label={`Rcv: ${formatObsTime(detail.received_at_utc)}`} />
        )}
        <MetaRow
          Icon={IconCoords}
          label={`${formatCoord(detail.latitude, 'lat')} ${formatCoord(detail.longitude, 'lon')}`}
        />
      </div>

      <div style={{ width: 1, height: 20, background: '#E5E7EB' }} />

      {/* Data freshness badge */}
      <FreshnessBadge freshness={dataFreshness ?? detail.data_freshness ?? 'DEMO'} />

      <div style={{ width: 1, height: 20, background: '#E5E7EB' }} />

      <span style={{
        background: '#F8FAFC', color: '#64748B',
        border: '1px solid #E2E8F0', borderRadius: 20,
        padding: '7px 12px', fontSize: 11, fontWeight: 600,
      }}>
        Source-tracked
      </span>
    </div>
  );
};

function Chip({ Icon, label }: { Icon: React.FC; label: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 5,
      background: '#F9FAFB',
      border: '1px solid #F3F4F6',
      borderRadius: 16,
      padding: '5px 11px',
      fontSize: 13, fontWeight: 500, color: '#374151',
    }}>
      <span style={{ color: '#6B7280', display: 'flex', alignItems: 'center' }}><Icon /></span>
      <span>{label}</span>
    </div>
  );
}

function MetaRow({ Icon, label }: { Icon: React.FC; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#6B7280' }}>
      <span style={{ display: 'flex', alignItems: 'center' }}><Icon /></span>
      <span style={{ fontFamily: "'Roboto Mono', 'Courier New', monospace" }}>{label}</span>
    </div>
  );
}

function StatusBadge({ online }: { online: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: online ? '#10B981' : '#EF4444', display: 'inline-block' }} />
      <span style={{ fontSize: 12, fontWeight: 500, color: '#6B7280' }}>
        System {online ? 'Online' : 'Offline'}
      </span>
    </div>
  );
}

const FRESHNESS_STYLES: Record<string, { bg: string; color: string; dot: string }> = {
  LIVE:       { bg: '#ECFDF5', color: '#065F46', dot: '#10B981' },
  DELAYED:    { bg: '#FFFBEB', color: '#92400E', dot: '#F59E0B' },
  STALE:      { bg: '#FEF3C7', color: '#78350F', dot: '#D97706' },
  HISTORICAL: { bg: '#F3F4F6', color: '#374151', dot: '#6B7280' },
  DEMO:       { bg: '#EEF2FF', color: '#3730A3', dot: '#6366F1' },
};

function FreshnessBadge({ freshness }: { freshness: string }) {
  const style = FRESHNESS_STYLES[freshness] ?? FRESHNESS_STYLES.DEMO;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 5,
      background: style.bg,
      borderRadius: 14,
      padding: '4px 10px',
      fontSize: 11, fontWeight: 700, color: style.color,
      letterSpacing: '0.05em',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: style.dot, display: 'inline-block' }} />
      {freshness}
    </div>
  );
}
