import React from 'react';

import type { AiDetectionStatus } from '../../types/cyclone';

interface Props {
  open: boolean;
  status: AiDetectionStatus | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

/** A small scientific-status drawer, never a substitute for official warnings. */
export const AiAnalysisPanel: React.FC<Props> = ({ open, status, loading, error, onClose }) => {
  if (!open) return null;
  const ready = status?.status === 'READY';

  return (
    <aside style={{
      position: 'absolute', top: 92, right: 12, zIndex: 40, width: 292,
      background: '#FFFFFF', border: '1px solid #E5E7EB', borderRadius: 8,
      boxShadow: '0 8px 24px rgba(17,24,39,0.14)', padding: 14,
    }} aria-label="AI analysis">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#111827', letterSpacing: '0.04em' }}>AI ANALYSIS</div>
          <div style={{ marginTop: 2, fontSize: 10, color: '#6B7280' }}>Research support only. Not an official warning.</div>
        </div>
        <button onClick={onClose} aria-label="Close AI analysis" title="Close" style={{ border: 0, background: 'transparent', color: '#6B7280', cursor: 'pointer', fontSize: 18, lineHeight: 1 }}>×</button>
      </div>

      {loading && <div style={{ fontSize: 12, color: '#6B7280' }}>Checking model availability...</div>}
      {error && <div style={{ fontSize: 12, lineHeight: 1.45, color: '#B91C1C' }}>AI analysis status could not be loaded.</div>}
      {!loading && !error && ready && (
        <div style={{ fontSize: 12, lineHeight: 1.5, color: '#374151' }}>
          <div style={{ fontWeight: 700, color: '#047857' }}>Detection model ready</div>
          <div style={{ marginTop: 5 }}>Model: {status.architecture ?? 'Recorded checkpoint'}</div>
          {status.model_version && <div>Version: {status.model_version}</div>}
          {status.dataset_version && <div>Dataset: {status.dataset_version}</div>}
          <div style={{ marginTop: 8, color: '#6B7280' }}>No inference is run until a validated satellite image is supplied to the backend.</div>
        </div>
      )}
      {!loading && !error && !ready && (
        <div style={{ fontSize: 12, lineHeight: 1.5, color: '#374151' }}>
          <div style={{ fontWeight: 700, color: '#6B7280' }}>Cyclone Detection</div>
          <div style={{ marginTop: 3, fontWeight: 600, color: '#111827' }}>Unavailable</div>
          <div style={{ marginTop: 7, color: '#6B7280' }}>Reason: {status?.reason ?? 'No trained detection model is currently available.'}</div>
          <div style={{ marginTop: 9, paddingTop: 9, borderTop: '1px solid #F3F4F6', color: '#6B7280' }}>AI prediction: not implemented in Phase 4.</div>
        </div>
      )}
    </aside>
  );
};
