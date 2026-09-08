"""
CycloneAI — SQLAlchemy ORM Models (Phase 2)

Tables:
  data_sources          — Registry of external meteorological data sources
  cyclone_records       — Raw ingested records (immutable audit log)
  cyclone_observations  — Normalised 6-hourly observations (append-only)
  cyclone_forecasts     — Official forecast track points
  satellite_layers      — Satellite layer metadata (Phase 2b stub)

Design rules:
  - cyclone_observations are NEVER overwritten — append-only
  - Source attribution is required on every row
  - received_at and processed_at are always recorded
  - Deduplication key: (cyclone_id, timestamp_utc) for observations
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# data_sources
# ---------------------------------------------------------------------------
class DataSource(Base):
    """Registry of external data sources with their status."""
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_type: Mapped[str] = mapped_column(
        String(32), default="none",
        comment="none | api_key | ip_whitelist | credentials"
    )
    update_frequency: Mapped[str | None] = mapped_column(
        String(32), nullable=True,
        comment="e.g. '6h', '3h', 'daily'"
    )
    last_fetched_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str] = mapped_column(
        String(32), default="unknown",
        comment="ok | error | unavailable | disabled"
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


# ---------------------------------------------------------------------------
# cyclone_records  (raw audit log — immutable)
# ---------------------------------------------------------------------------
class CycloneRecord(Base):
    """
    Raw ingested record from an external source.
    One row per source row — never modified after insert.
    """
    __tablename__ = "cyclone_records"
    __table_args__ = (
        UniqueConstraint("sid", "timestamp_utc", "source", name="uq_record_sid_ts_src"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Storm identity
    sid: Mapped[str] = mapped_column(String(32), nullable=False, index=True,
                                      comment="IBTrACS SID or internal identifier")
    cyclone_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    basin: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Observation time
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Position
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # Intensity (raw — units as received)
    wind_speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_unit: Mapped[str] = mapped_column(String(8), default="kt")
    central_pressure: Mapped[float | None] = mapped_column(Float, nullable=True)
    intensity_category: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Movement
    movement_direction: Mapped[str | None] = mapped_column(String(8), nullable=True)
    movement_speed: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Provenance
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    processed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True,
                                                  comment="Original CSV row or JSON string")


# ---------------------------------------------------------------------------
# cyclone_observations  (normalised — append-only)
# ---------------------------------------------------------------------------
class CycloneObservation(Base):
    """
    Normalised observation. Units are always:
      wind_speed_kmh  — km/h (converted from knots if needed)
      pressure_hpa    — hPa / mb
    Append-only: never UPDATE, only INSERT.
    Natural dedup key: (cyclone_id, timestamp_utc).
    """
    __tablename__ = "cyclone_observations"
    __table_args__ = (
        UniqueConstraint("cyclone_id", "timestamp_utc", name="uq_obs_id_ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identity
    cyclone_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    cyclone_name: Mapped[str] = mapped_column(String(64), nullable=False)
    basin: Mapped[str] = mapped_column(String(8), nullable=False)

    # Observation
    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # Normalised intensity (km/h, hPa)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_hpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    intensity_category: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Movement
    movement_direction: Mapped[str | None] = mapped_column(String(8), nullable=True)
    movement_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Provenance
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Freshness at time of processing
    data_freshness: Mapped[str] = mapped_column(
        String(16), nullable=False,
        comment="LIVE | DELAYED | STALE | HISTORICAL | DEMO"
    )


# ---------------------------------------------------------------------------
# cyclone_forecasts  (official forecast — separate from observed)
# ---------------------------------------------------------------------------
class CycloneForecast(Base):
    """
    Official forecast track point from RSMC New Delhi or IMD.
    Distinct from observed track. Displayed as dashed line on map.
    """
    __tablename__ = "cyclone_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "cyclone_id", "issued_at_utc", "valid_at_utc",
            name="uq_forecast_id_issued_valid"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    cyclone_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    cyclone_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # When this forecast was issued
    issued_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # When this forecast point is valid (actual time being forecast)
    valid_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Forecast lead time in hours (+6, +12, +24, +48, +72, +96, +120)
    forecast_hour: Mapped[int] = mapped_column(Integer, nullable=False)

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_hpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    intensity_category: Mapped[str | None] = mapped_column(String(64), nullable=True)

    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ---------------------------------------------------------------------------
# satellite_layers  (Phase 2b architecture stub)
# ---------------------------------------------------------------------------
class SatelliteLayer(Base):
    """
    Satellite layer metadata.
    Phase 2b: architecture only. No actual tiles are served until
    a real source (INSAT-3DR / MOSDAC) is integrated.
    """
    __tablename__ = "satellite_layers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str | None] = mapped_column(
        String(8), nullable=True,
        comment="VIS | IR | WV"
    )
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Geographic bounding box
    bbox_north: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_south: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_east: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_west: Mapped[float | None] = mapped_column(Float, nullable=True)

    timestamp_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    opacity: Mapped[float] = mapped_column(Float, default=1.0)
    available: Mapped[bool] = mapped_column(Boolean, default=False)
