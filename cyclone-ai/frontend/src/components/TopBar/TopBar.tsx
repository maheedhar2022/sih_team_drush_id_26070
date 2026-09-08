/**
 * CycloneAI — TopBar
 * Floating pill-shaped top bar showing selected cyclone details.
 */
import React from 'react';
import type { CycloneDetail, HealthResponse } from '../../types/cyclone';

interface Props {
  detail: CycloneDetail | null;
  health: HealthResponse | null;
}

export const TopBar: React.FC<Props> = ({ detail, health }) => {
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
      display: 'flex', alignItems: 'center', gap: 16,
      border: '1px solid #E5E7EB',
    }}>
      {/* Name and Status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 15, fontWeight: 700, color: '#111827' }}>{detail.name}</span>
        {detail.status === 'ACTIVE' && (
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#EF4444' }} />
        )}
      </div>

      <div style={{ width: 1, height: 20, background: '#E5E7EB' }} />

      {/* Info Chips */}
      <div style={{ display: 'flex', gap: 8 }}>
        <Chip icon="💨" label={`${detail.wind_speed_kmh ?? '--'} km/h`} />
        <Chip icon="⏱️" label={`${detail.pressure_hpa ?? '--'} hPa`} />
        <Chip icon="🧭" label={detail.movement_direction ?? '--'} />
      </div>

      <div style={{ width: 1, height: 20, background: '#E5E7EB' }} />

      {/* AI Button */}
      <button style={{
        background: '#111827', color: '#FFFFFF',
        border: 'none', borderRadius: 20,
        padding: '8px 16px',
        fontSize: 13, fontWeight: 500,
        cursor: 'pointer',
      }}>
        View AI Analysis
      </button>
    </div>
  );
};

function Chip({ icon, label }: { icon: string; label: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      background: '#F9FAFB',
      border: '1px solid #F3F4F6',
      borderRadius: 16,
      padding: '6px 12px',
      fontSize: 13, fontWeight: 500, color: '#4B5563',
    }}>
      <span>{icon}</span>
      <span>{label}</span>
    </div>
  );
}

function StatusBadge({ online }: { online: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: online ? '#10B981' : '#EF4444' }} />
      <span style={{ fontSize: 12, fontWeight: 500, color: '#6B7280' }}>
        System {online ? 'Online' : 'Offline'}
      </span>
    </div>
  );
}
