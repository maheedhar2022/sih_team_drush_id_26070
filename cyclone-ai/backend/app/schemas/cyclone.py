"""
CycloneAI Backend — Pydantic Schemas (Phase 2)

All data-transfer models used across API responses.
New in Phase 2: DataFreshness, ObservationRecord, ForecastPoint,
                ForecastTrack, DataSourceInfo, SatelliteLayerSpec
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class DataMode(str, Enum):
    """Distinguishes real/live data from demo/historical data."""
    LIVE = "LIVE"
    DEMO = "DEMO"
    DELAYED = "DELAYED"
    OFFLINE = "OFFLINE"
    HISTORICAL = "HISTORICAL"


class DataFreshness(str, Enum):
    """
    Freshness of an observation relative to the current time.
    LIVE     — observation < 6h old
    DELAYED  — observation 6–24h old
    STALE    — observation > 24h old, < 1 year
    HISTORICAL — observation > 1 year old
    DEMO     — hard-coded demo data (no real fetch)
    """
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    STALE = "STALE"
    HISTORICAL = "HISTORICAL"
    DEMO = "DEMO"


class CycloneStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DISSIPATED = "DISSIPATED"


class IntensityCategory(str, Enum):
    DEPRESSION = "Depression"
    DEEP_DEPRESSION = "Deep Depression"
    CYCLONIC_STORM = "Cyclonic Storm"
    SEVERE_CYCLONIC_STORM = "Severe Cyclonic Storm"
    VERY_SEVERE = "Very Severe Cyclonic Storm"
    EXTREMELY_SEVERE = "Extremely Severe Cyclonic Storm"
    SUPER = "Super Cyclonic Storm"


class Basin(str, Enum):
    NI = "NI"   # North Indian Ocean (BoB + Arabian Sea)
    NA = "NA"
    EP = "EP"
    WP = "WP"
    SP = "SP"
    SI = "SI"
    SA = "SA"


# ---------------------------------------------------------------------------
# Core Track Models
# ---------------------------------------------------------------------------

class TrackPoint(BaseModel):
    """A single point in a cyclone observed track."""
    timestamp: datetime
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    wind_speed_kmh: Optional[float] = Field(None, description="Maximum sustained wind speed in km/h")
    pressure_hpa: Optional[float] = Field(None, description="Central pressure in hPa")
    intensity: Optional[IntensityCategory] = None
    source: str
    data_freshness: Optional[DataFreshness] = None


class ForecastPoint(BaseModel):
    """A single official forecast track point."""
    issued_at_utc: datetime
    valid_at_utc: datetime
    forecast_hour: int = Field(..., description="Lead time in hours (+6, +12, +24, etc.)")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    wind_speed_kmh: Optional[float] = None
    pressure_hpa: Optional[float] = None
    intensity: Optional[IntensityCategory] = None
    source: str
    source_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Cyclone Summary & Detail
# ---------------------------------------------------------------------------

class Cyclone(BaseModel):
    """Summary representation of a tropical cyclone."""
    id: str
    name: str
    basin: Basin
    status: CycloneStatus
    data_mode: DataMode
    data_freshness: DataFreshness = DataFreshness.DEMO

    # Current position (latest observation)
    latitude: float
    longitude: float
    wind_speed_kmh: Optional[float] = None
    pressure_hpa: Optional[float] = None
    intensity: Optional[IntensityCategory] = None
    movement_direction: Optional[str] = None
    movement_speed_kmh: Optional[float] = None

    # Timestamps
    last_observation_utc: datetime
    received_at_utc: Optional[datetime] = None
    source: str
    source_url: Optional[str] = None

    # Metadata
    year: int
    season: str


class CycloneDetail(Cyclone):
    """Extended cyclone detail."""
    description: Optional[str] = None
    peak_wind_kmh: Optional[float] = None
    peak_intensity: Optional[IntensityCategory] = None
    landfall_expected: Optional[bool] = None
    affected_regions: List[str] = []


class CycloneTrack(BaseModel):
    """Complete observed track for a cyclone."""
    cyclone_id: str
    cyclone_name: str
    data_mode: DataMode
    source: str
    points: List[TrackPoint]


class ForecastTrack(BaseModel):
    """
    Official forecast track from RSMC New Delhi / IMD.
    Rendered as a dashed line on the map — distinct from observed track.
    """
    cyclone_id: str
    cyclone_name: str
    issued_at_utc: datetime
    source: str
    source_url: Optional[str] = None
    points: List[ForecastPoint]


# ---------------------------------------------------------------------------
# Data Source Info
# ---------------------------------------------------------------------------

class DataSourceInfo(BaseModel):
    """
    Metadata about a data source — for source transparency panel.
    Displayed in the frontend with full provenance.
    """
    name: str
    display_name: str
    url: Optional[str] = None
    auth_type: str = "none"
    update_frequency: Optional[str] = None
    last_fetched_utc: Optional[datetime] = None
    last_status: str = "unknown"
    last_error: Optional[str] = None
    enabled: bool = True


# ---------------------------------------------------------------------------
# Satellite Layer (Phase 2b Architecture Stub)
# ---------------------------------------------------------------------------

class SatelliteLayerSpec(BaseModel):
    """
    Specification for a satellite imagery layer.
    Phase 2b: architecture only — no tiles served until source integrated.
    """
    id: str
    name: str
    channel: Optional[str] = None     # VIS | IR | WV
    source: Optional[str] = None
    source_url: Optional[str] = None
    timestamp_utc: Optional[datetime] = None
    tile_url: Optional[str] = None
    bbox: Optional[Dict[str, float]] = None   # N, S, E, W
    opacity: float = 1.0
    available: bool = False
    unavailable_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Health / System
# ---------------------------------------------------------------------------

class SystemStatus(str, Enum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"


class HealthResponse(BaseModel):
    status: SystemStatus
    version: str
    demo_mode: bool
    data_mode: DataMode
    device: str
    timestamp_utc: datetime
    uptime_seconds: Optional[float] = None
    sources: dict = Field(default_factory=dict)
    # Phase 2 additions
    provider_statuses: dict = Field(default_factory=dict)
    last_ingestion_utc: Optional[datetime] = None
    active_ni_storms: int = 0


# ---------------------------------------------------------------------------
# API List Wrappers
# ---------------------------------------------------------------------------

class ActiveCyclonesResponse(BaseModel):
    data_mode: DataMode
    data_freshness: DataFreshness = DataFreshness.DEMO
    count: int
    cyclones: List[Cyclone]
    retrieved_at_utc: datetime
    source: str
    note: Optional[str] = None


class DataSourcesResponse(BaseModel):
    sources: List[DataSourceInfo]
    retrieved_at_utc: datetime
