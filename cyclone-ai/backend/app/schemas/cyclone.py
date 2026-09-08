"""
CycloneAI Backend — Pydantic Schemas

All data-transfer models used across API responses.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

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
# Core Models
# ---------------------------------------------------------------------------

class TrackPoint(BaseModel):
    """A single point in a cyclone track."""
    timestamp: datetime
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    wind_speed_kmh: Optional[float] = Field(None, description="Maximum sustained wind speed in km/h")
    pressure_hpa: Optional[float] = Field(None, description="Central pressure in hPa")
    intensity: Optional[IntensityCategory] = None
    source: str = "IBTrACS"


class Cyclone(BaseModel):
    """Summary representation of a tropical cyclone."""
    id: str
    name: str
    basin: Basin
    status: CycloneStatus
    data_mode: DataMode

    # Current position (latest observation)
    latitude: float
    longitude: float
    wind_speed_kmh: Optional[float] = None
    pressure_hpa: Optional[float] = None
    intensity: Optional[IntensityCategory] = None
    movement_direction: Optional[str] = None   # e.g. "NNW"
    movement_speed_kmh: Optional[float] = None

    # Timestamps
    last_observation_utc: datetime
    source: str

    # Metadata
    year: int
    season: str


class CycloneDetail(Cyclone):
    """Extended cyclone detail including track and description."""
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
    device: str                       # cuda | cpu
    timestamp_utc: datetime
    uptime_seconds: Optional[float] = None
    sources: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# API List Wrappers
# ---------------------------------------------------------------------------

class ActiveCyclonesResponse(BaseModel):
    data_mode: DataMode
    count: int
    cyclones: List[Cyclone]
    retrieved_at_utc: datetime
    source: str
    note: Optional[str] = None
