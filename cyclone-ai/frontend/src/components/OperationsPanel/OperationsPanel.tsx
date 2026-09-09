import React from 'react';
import type {
  CycloneDetail,
  CycloneTrack,
  DataSourcesResponse,
  ForecastTrack,
  HealthResponse,
  SatelliteCatalogStatus,
  SatelliteLayerSpec,
  SatelliteObservation,
} from '../../types/cyclone';

interface Props {
  detail: CycloneDetail | null;
  track: CycloneTrack | null;
  forecastTrack: ForecastTrack | null;
  health: HealthResponse | null;
  dataSources: DataSourcesResponse | null;
  dataSourcesLoading: boolean;
  satelliteLayers: SatelliteLayerSpec[];
  satelliteCatalogStatus: SatelliteCatalogStatus | null;
  latestSatelliteObservation: SatelliteObservation | null;
}

const IconPulse = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 12 7 12 10 4 14 20 17 12 21 12" />
  </svg>
);

const IconSatellite = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="m13 7 4-4 4 4-4 4" /><path d="M17 3 7 13" />
    <path d="M5 15 3 21l6-2" /><path d="M8 16 4 12" />
  </svg>
);

const IconDatabase = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7" />
  </svg>
);

function formatTime(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().replace('T', ' ').replace('.000Z', ' UTC');
}

function statusColor(status: string | undefined): string {
  if (status === 'ok' || status === 'ONLINE' || status === 'READY') return '#047857';
  if (status === 'error' || status === 'OFFLINE') return '#B91C1C';
  return '#B45309';
}

export const OperationsPanel: React.FC<Props> = ({
  detail, track, forecastTrack, health, dataSources, dataSourcesLoading,
  satelliteLayers, satelliteCatalogStatus, latestSatelliteObservation,
}) => {
  const availableLayers = satelliteLayers.filter(layer => layer.available).length;
  const feedSources = dataSources?.sources ?? [];

  return (
    <aside className="operations-panel" aria-label="Cyclone operations summary">
      <div className="operations-header">
        <div>
          <div className="eyebrow">OPERATIONS CONSOLE</div>
          <h1>{detail?.name ?? 'North Indian Ocean'}</h1>
        </div>
        <span className={`system-dot ${health?.status === 'ONLINE' ? 'online' : 'offline'}`} title={health?.status ?? 'Checking system'} />
      </div>

      <section className="operations-section">
        <div className="section-heading"><IconPulse /><span>Observation</span></div>
        {detail ? (
          <>
            <div className="metric-grid">
              <Metric label="Wind" value={`${detail.wind_speed_kmh ?? '—'} km/h`} />
              <Metric label="Pressure" value={`${detail.pressure_hpa ?? '—'} hPa`} />
              <Metric label="Position" value={`${detail.latitude.toFixed(2)}°, ${detail.longitude.toFixed(2)}°`} />
              <Metric label="Movement" value={detail.movement_direction ?? '—'} />
            </div>
            <div className="observation-meta">
              <span>Last observation</span>
              <strong>{formatTime(detail.last_observation_utc)}</strong>
            </div>
          </>
        ) : (
          <div className="empty-state">Select a system to inspect its observation.</div>
        )}
      </section>

      <section className="operations-section">
        <div className="section-heading"><IconDatabase /><span>Track products</span></div>
        <div className="product-row">
          <div><strong>Observed track</strong><span>{track?.source ?? 'Waiting for source'}</span></div>
          <b>{track?.points.length ?? 0}<small> pts</small></b>
        </div>
        <div className="product-row">
          <div><strong>Official forecast</strong><span>{forecastTrack?.source ?? 'Not available'}</span></div>
          <b className={forecastTrack ? 'value-good' : 'value-muted'}>{forecastTrack?.points.length ?? 0}<small> pts</small></b>
        </div>
      </section>

      <section className="operations-section">
        <div className="section-heading"><IconSatellite /><span>Satellite feeds</span></div>
        <div className="feed-summary">
          <div><strong>NASA GIBS</strong><span>Public raster imagery</span></div>
          <StatusValue value={`${availableLayers}/${satelliteLayers.length} ready`} good={availableLayers > 0} />
        </div>
        <div className="feed-summary">
          <div><strong>INSAT / MOSDAC</strong><span>{latestSatelliteObservation?.product_id ?? 'Catalog metadata'}</span></div>
          <StatusValue value={satelliteCatalogStatus?.catalog_state ?? 'CHECKING'} good={satelliteCatalogStatus?.catalog_state === 'READY'} />
        </div>
        {latestSatelliteObservation && (
          <div className="source-note">
            {latestSatelliteObservation.satellite} · {formatTime(latestSatelliteObservation.observation_timestamp_utc)}
          </div>
        )}
      </section>

      <section className="operations-section sources-section">
        <div className="section-heading"><IconDatabase /><span>Source health</span></div>
        {dataSourcesLoading && <div className="empty-state">Checking providers...</div>}
        {!dataSourcesLoading && feedSources.length === 0 && <div className="empty-state">No provider status reported.</div>}
        {feedSources.map(source => (
          <div className="source-row" key={source.name}>
            <span className="source-indicator" style={{ background: statusColor(source.last_status) }} />
            <div><strong>{source.display_name}</strong><span>{source.last_status} · {source.update_frequency ?? 'on demand'}</span></div>
          </div>
        ))}
      </section>

      <div className="operations-footer">
        <span>API {health?.version ?? '—'}</span>
        <span>Checked {formatTime(health?.timestamp_utc)}</span>
      </div>
    </aside>
  );
};

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function StatusValue({ value, good }: { value: string; good: boolean }) {
  return <span className={good ? 'status-value good' : 'status-value'}>{value}</span>;
}
