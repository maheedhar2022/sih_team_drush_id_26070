/**
 * AiAnalysisPanel — Phase 5 Intensity Classification & Estimation
 *
 * Displays:
 *  • Detection model readiness (Phase 4)
 *  • Intensity model readiness (Phase 5)
 *  • Image upload button to trigger real inference
 *  • Inference results: category, confidence, wind, pressure
 *  • Official observation clearly separated from AI estimate
 *  • All model states: idle / loading / success / error / model_unavailable
 *
 * Rules:
 *  - Never shows fabricated values.
 *  - Shows MODEL_NOT_TRAINED verbatim when no checkpoint is available.
 *  - Official meteorological data is never overwritten by AI values.
 */
import React, { useCallback, useRef } from 'react';

import { useAiIntensity } from '../../hooks/useAiIntensity';
import type { AiDetectionStatus, AiIntensityStatus, CycloneDetail } from '../../types/cyclone';

// ── colour tokens ----------------------------------------------------------

const C = {
  ready: '#047857',
  readyBg: '#ECFDF5',
  warn: '#B45309',
  warnBg: '#FEF3C7',
  err: '#B91C1C',
  errBg: '#FEF2F2',
  mid: '#374151',
  muted: '#6B7280',
  border: '#E5E7EB',
  borderLight: '#F3F4F6',
  label: '#9CA3AF',
  aiAccent: '#4F46E5',
  aiBg: '#EEF2FF',
};

// ── icons (inline SVG, no emoji) -------------------------------------------

const IconUpload = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="16 16 12 12 8 16" /><line x1="12" y1="12" x2="12" y2="21" />
    <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3" />
  </svg>
);

const IconSpinner = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
    style={{ animation: 'cyclone-spin 0.9s linear infinite', display: 'inline-block' }}>
    <path d="M21 12a9 9 0 1 1-6.22-8.56" />
  </svg>
);

const IconClose = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

// ── sub-components ---------------------------------------------------------

function Row({ label, value, accent }: { label: string; value: React.ReactNode; accent?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
      <span style={{ fontSize: 11, color: C.label, flexShrink: 0 }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 600, color: accent ? C.aiAccent : C.mid, textAlign: 'right' }}>{value}</span>
    </div>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 10, fontWeight: 700, color: C.label, letterSpacing: '0.07em', textTransform: 'uppercase', marginBottom: 8 }}>
      {children}
    </div>
  );
}

function Pill({ text, bg, fg }: { text: string; bg: string; fg: string }) {
  return (
    <span style={{ display: 'inline-block', fontSize: 10, fontWeight: 700, background: bg, color: fg, borderRadius: 4, padding: '2px 6px', letterSpacing: '0.04em' }}>
      {text}
    </span>
  );
}

// ── confidence bar ---------------------------------------------------------

function ConfidenceBar({ pct }: { pct: number }) {
  const colour = pct >= 0.75 ? C.ready : pct >= 0.5 ? C.warn : C.err;
  return (
    <div style={{ marginTop: 2, marginBottom: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: C.muted, marginBottom: 3 }}>
        <span>Confidence</span>
        <span style={{ fontWeight: 700, color: colour }}>{(pct * 100).toFixed(1)}%</span>
      </div>
      <div style={{ height: 5, borderRadius: 3, background: C.borderLight, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${(pct * 100).toFixed(1)}%`, background: colour, borderRadius: 3, transition: 'width 0.4s ease' }} />
      </div>
    </div>
  );
}

// ── Props ------------------------------------------------------------------

interface Props {
  open: boolean;
  onClose: () => void;
  // Detection (Phase 4)
  status: AiDetectionStatus | null;
  loading: boolean;
  error: string | null;
  // Intensity readiness (Phase 5 status poll)
  intensityStatus: AiIntensityStatus | null;
  intensityLoading: boolean;
  intensityError: string | null;
  // Optional: currently selected cyclone for official data display
  selectedCyclone?: CycloneDetail | null;
}

// ── Main component ---------------------------------------------------------

/** A compact, scientific-status drawer for Phase 5 AI analysis.
 *  Never a substitute for official IMD/RSMC warnings. */
export const AiAnalysisPanel: React.FC<Props> = ({
  open, onClose,
  status, loading, error,
  intensityStatus, intensityLoading, intensityError,
  selectedCyclone,
}) => {
  const { state: inferenceState, run: runInference, reset: resetInference } = useAiIntensity();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // Clear the input so the same file can be re-selected
    e.target.value = '';
    void runInference(file, 'user_upload');
  }, [runInference]);

  const triggerUpload = useCallback(() => fileInputRef.current?.click(), []);

  if (!open) return null;

  const detectionReady = status?.status === 'READY';
  const intensityModelReady = intensityStatus?.status === 'READY';

  // Determine if we can show the upload button
  const canUpload = intensityModelReady && inferenceState.phase !== 'loading';
  const isInferring = inferenceState.phase === 'loading';

  // Extract intensity result when available
  const result = inferenceState.phase === 'success' ? inferenceState.result : null;
  const resultIsModel = result?.status === 'success';

  return (
    <>
      {/* Spinner keyframe — injected once as a style tag */}
      <style>{`@keyframes cyclone-spin{to{transform:rotate(360deg)}}`}</style>

      <aside
        id="ai-analysis-panel"
        aria-label="AI analysis panel"
        style={{
          position: 'absolute', top: 92, right: 12, zIndex: 40, width: 300,
          background: '#FFFFFF', border: `1px solid ${C.border}`, borderRadius: 10,
          boxShadow: '0 10px 32px rgba(17,24,39,0.13)', padding: 16,
          display: 'flex', flexDirection: 'column', gap: 0,
          maxHeight: 'calc(100vh - 120px)', overflowY: 'auto',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: '#111827', letterSpacing: '0.03em' }}>AI ANALYSIS</div>
            <div style={{ marginTop: 2, fontSize: 10, color: C.muted, lineHeight: 1.4 }}>
              Research support only. Not an official warning.
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close AI analysis panel"
            id="ai-panel-close"
            style={{ border: 0, background: 'transparent', color: C.muted, cursor: 'pointer', padding: 2, lineHeight: 1, marginTop: -2 }}
          >
            <IconClose />
          </button>
        </div>

        {/* ── OFFICIAL OBSERVATION ──────────────────────────────────────── */}
        {selectedCyclone && (
          <>
            <div style={{ borderTop: `1px solid ${C.borderLight}`, paddingTop: 12, marginBottom: 12 }}>
              <SectionHeader>Official Observation</SectionHeader>
              <div style={{ marginBottom: 6 }}>
                <Pill text="IMD / RSMC" bg={C.readyBg} fg={C.ready} />
              </div>
              {selectedCyclone.intensity && <Row label="Category" value={selectedCyclone.intensity} />}
              {selectedCyclone.wind_speed_kmh != null && (
                <Row label="Wind" value={`${selectedCyclone.wind_speed_kmh} km/h`} />
              )}
              {selectedCyclone.pressure_hpa != null && (
                <Row label="Pressure" value={`${selectedCyclone.pressure_hpa} hPa`} />
              )}
              {!selectedCyclone.intensity && selectedCyclone.wind_speed_kmh == null && selectedCyclone.pressure_hpa == null && (
                <div style={{ fontSize: 12, color: C.muted }}>No official observation available.</div>
              )}
            </div>
          </>
        )}

        {/* ── CYCLONE DETECTION (Phase 4) ───────────────────────────────── */}
        <div style={{ borderTop: `1px solid ${C.borderLight}`, paddingTop: 12, marginBottom: 12 }}>
          <SectionHeader>Cyclone Detection</SectionHeader>
          {loading && <div style={{ fontSize: 12, color: C.muted }}>Checking model availability…</div>}
          {error && <div style={{ fontSize: 12, color: C.err }}>Status could not be loaded.</div>}
          {!loading && !error && detectionReady && (
            <div style={{ fontSize: 12, color: C.ready, fontWeight: 600 }}>
              Model ready — {status?.architecture ?? 'checkpoint'}
              {status?.dataset_version && <span style={{ color: C.muted, fontWeight: 400 }}> · {status.dataset_version}</span>}
            </div>
          )}
          {!loading && !error && !detectionReady && (
            <div style={{ fontSize: 12, color: C.muted }}>
              <span style={{ fontWeight: 600, color: '#374151' }}>Unavailable. </span>
              {status?.reason ?? 'No trained detection model is currently available.'}
            </div>
          )}
        </div>

        {/* ── AI INTENSITY ESTIMATION (Phase 5) ────────────────────────── */}
        <div style={{ borderTop: `1px solid ${C.borderLight}`, paddingTop: 12 }}>
          <SectionHeader>Intensity Classification &amp; Estimation</SectionHeader>

          {/* Model status row */}
          {intensityLoading && (
            <div style={{ fontSize: 12, color: C.muted, marginBottom: 8 }}>
              <IconSpinner /> Checking model availability…
            </div>
          )}
          {intensityError && (
            <div style={{ fontSize: 12, color: C.err, marginBottom: 8 }}>
              Intensity status could not be loaded.
            </div>
          )}

          {!intensityLoading && !intensityError && intensityModelReady && (
            <div style={{ fontSize: 11, color: C.ready, fontWeight: 600, marginBottom: 8 }}>
              Model ready — {intensityStatus?.architecture ?? 'checkpoint'}
              {intensityStatus?.dataset_version && (
                <span style={{ color: C.muted, fontWeight: 400 }}> · {intensityStatus.dataset_version}</span>
              )}
            </div>
          )}
          {!intensityLoading && !intensityError && !intensityModelReady && (
            <div style={{ fontSize: 11, color: C.muted, marginBottom: 8 }}>
              <span style={{ fontWeight: 600, color: C.mid }}>
                {intensityStatus?.status === 'MODEL_NOT_TRAINED' ? 'Model not trained.' : 'Unavailable.'}
              </span>{' '}
              {intensityStatus?.reason ?? 'No trained intensity model is currently available.'}
            </div>
          )}

          {/* Upload button */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            style={{ display: 'none' }}
            aria-label="Select satellite image for AI intensity analysis"
            onChange={handleFileChange}
            id="ai-intensity-file-input"
          />
          <button
            id="ai-intensity-upload-btn"
            onClick={triggerUpload}
            disabled={!canUpload}
            aria-label={
              !intensityModelReady
                ? 'Intensity model not available'
                : 'Upload satellite image for AI intensity analysis'
            }
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              width: '100%', padding: '8px 10px',
              background: canUpload ? C.aiBg : C.borderLight,
              border: `1px solid ${canUpload ? C.aiAccent : C.border}`,
              borderRadius: 6, cursor: canUpload ? 'pointer' : 'not-allowed',
              color: canUpload ? C.aiAccent : C.muted,
              fontSize: 12, fontWeight: 600,
              transition: 'all 0.15s',
              marginBottom: 10,
            }}
          >
            {isInferring ? <IconSpinner /> : <IconUpload />}
            {isInferring ? 'Analysing image…' : 'Upload image for AI analysis'}
          </button>

          {/* ── Inference states ────────────────────────────────────────── */}

          {/* Idle (no inference yet) */}
          {inferenceState.phase === 'idle' && intensityModelReady && (
            <div style={{ fontSize: 11, color: C.muted, lineHeight: 1.5 }}>
              Upload a JPEG, PNG, or WebP satellite image. The model will return an intensity category,
              confidence, wind estimate, and pressure estimate.
            </div>
          )}

          {/* Network / API error */}
          {inferenceState.phase === 'error' && (
            <div style={{ background: C.errBg, border: `1px solid #FCA5A5`, borderRadius: 6, padding: '8px 10px', fontSize: 12 }}>
              <div style={{ fontWeight: 700, color: C.err, marginBottom: 2 }}>Inference failed</div>
              <div style={{ color: '#7F1D1D', lineHeight: 1.45 }}>{inferenceState.message}</div>
              <button onClick={resetInference} id="ai-intensity-reset-btn"
                style={{ marginTop: 6, background: 'none', border: 'none', color: C.aiAccent, cursor: 'pointer', fontSize: 11, padding: 0, fontWeight: 600 }}>
                Try again
              </button>
            </div>
          )}

          {/* Success (result rendered) */}
          {inferenceState.phase === 'success' && result && (
            <div style={{ background: C.aiBg, border: `1px solid #C7D2FE`, borderRadius: 6, padding: '10px 12px', marginBottom: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: C.aiAccent, letterSpacing: '0.06em', textTransform: 'uppercase' }}>AI ESTIMATE</div>
                <Pill text="EXPERIMENTAL" bg="#EDE9FE" fg="#5B21B6" />
              </div>

              {!resultIsModel && (
                <div style={{ fontSize: 12, color: C.err, fontWeight: 600, marginBottom: 4 }}>
                  {result.status === 'MODEL_NOT_TRAINED'
                    ? 'Model not trained — no prediction available.'
                    : result.reason ?? `Inference failed (${result.status}).`}
                </div>
              )}

              {resultIsModel && (
                <>
                  {result.category && (
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#1E1B4B', marginBottom: 6 }}>
                      {result.category}
                    </div>
                  )}
                  {result.confidence != null && <ConfidenceBar pct={result.confidence} />}

                  {result.wind_speed_kmh != null && (
                    <Row label="AI Wind" value={`${result.wind_speed_kmh.toFixed(1)} km/h`} accent />
                  )}
                  {result.central_pressure_hpa != null && (
                    <Row label="AI Pressure" value={`${result.central_pressure_hpa.toFixed(1)} hPa`} accent />
                  )}

                  {result.model_version && (
                    <div style={{ marginTop: 6, fontSize: 10, color: C.muted }}>
                      Model: {result.model_version}
                      {result.architecture && ` · ${result.architecture}`}
                    </div>
                  )}
                  {result.inference_timestamp_utc && (
                    <div style={{ fontSize: 10, color: C.muted }}>
                      {new Date(result.inference_timestamp_utc).toUTCString()}
                    </div>
                  )}

                  {/* Official vs AI notice */}
                  <div style={{
                    marginTop: 8, padding: '6px 8px', background: '#FFFBEB',
                    border: '1px solid #FDE68A', borderRadius: 4, fontSize: 10, color: '#78350F', lineHeight: 1.4,
                  }}>
                    AI estimates are experimental. Always follow official IMD / RSMC warnings.
                  </div>

                  {/* Class probabilities (collapsible list) */}
                  {result.class_probabilities && Object.keys(result.class_probabilities).length > 0 && (
                    <details style={{ marginTop: 8 }}>
                      <summary style={{ fontSize: 11, color: C.muted, cursor: 'pointer', userSelect: 'none' }}>
                        All class probabilities
                      </summary>
                      <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 3 }}>
                        {Object.entries(result.class_probabilities)
                          .sort(([, a], [, b]) => b - a)
                          .map(([cls, prob]) => (
                            <div key={cls} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                              <span style={{ color: C.mid, flex: 1, marginRight: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{cls}</span>
                              <span style={{ color: C.aiAccent, fontWeight: 600, flexShrink: 0 }}>{(prob * 100).toFixed(1)}%</span>
                            </div>
                          ))}
                      </div>
                    </details>
                  )}
                </>
              )}

              <button onClick={resetInference} id="ai-intensity-clear-btn"
                style={{ marginTop: 8, background: 'none', border: 'none', color: C.muted, cursor: 'pointer', fontSize: 11, padding: 0 }}>
                Clear result
              </button>
            </div>
          )}

          {/* Footer note */}
          <div style={{ marginTop: 10, fontSize: 10, color: C.muted, lineHeight: 1.45 }}>
            Official observed intensity remains separate from AI analysis.
            AI outputs must never replace authoritative meteorological advisories.
          </div>
        </div>
      </aside>
    </>
  );
};
