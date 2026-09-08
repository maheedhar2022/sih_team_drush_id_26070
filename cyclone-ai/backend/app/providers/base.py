"""
CycloneAI — Abstract Provider Base (Phase 2)

All meteorological data providers must implement CycloneDataProvider.
The provider abstraction ensures:
  - Frontend never depends on a specific external API
  - Source attribution is always present
  - Failures are explicit — never silently substituted
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

logger = logging.getLogger("cyclone_ai.providers")


class ProviderStatus(str, Enum):
    """Current operational status of a provider."""
    OK = "ok"
    ERROR = "error"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    STALE = "stale"


@dataclass
class RawObservation:
    """
    A single raw observation from a data provider.
    All required provenance fields must be populated.
    """
    # Storm identity
    cyclone_id: str
    cyclone_name: str
    basin: str

    # Observation
    timestamp_utc: datetime
    latitude: float
    longitude: float

    # Intensity (raw units from source)
    wind_speed: Optional[float]
    wind_unit: str          # 'kt' | 'kmh' | 'm/s'
    central_pressure: Optional[float]   # hPa / mb
    intensity_category: Optional[str]

    # Movement
    movement_direction: Optional[str]
    movement_speed: Optional[float]     # in wind_unit equivalent

    # Provenance — REQUIRED
    source: str             # e.g. "IBTrACS v04r01 / NEWDELHI"
    source_url: Optional[str]
    received_at_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Optional raw payload for audit log
    raw_data: Optional[str] = None


@dataclass
class RawForecastPoint:
    """An official forecast track point from a provider."""
    cyclone_id: str
    cyclone_name: str
    issued_at_utc: datetime
    valid_at_utc: datetime
    forecast_hour: int
    latitude: float
    longitude: float
    wind_speed_kmh: Optional[float]
    pressure_hpa: Optional[float]
    intensity_category: Optional[str]
    source: str
    source_url: Optional[str]
    received_at_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ProviderResult:
    """Result returned by a provider fetch call."""
    provider_name: str
    status: ProviderStatus
    observations: List[RawObservation] = field(default_factory=list)
    forecasts: List[RawForecastPoint] = field(default_factory=list)
    fetched_at_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None
    source_url: Optional[str] = None


class CycloneDataProvider(ABC):
    """
    Abstract base class for all meteorological data providers.

    Subclasses:
      IBTracsProvider      — IBTrACS ACTIVE CSV (NOAA NCEI, public)
      RSMCBulletinProvider — RSMC New Delhi text bulletins (scraped)
      HistoricalProvider   — Verified IMD/RSMC historical dataset
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique short identifier, e.g. 'ibtracs', 'rsmc_bulletin'."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for UI display."""
        ...

    @property
    @abstractmethod
    def source_url(self) -> Optional[str]:
        """Primary URL of the data source (for attribution)."""
        ...

    @property
    @abstractmethod
    def update_frequency(self) -> str:
        """How often data refreshes, e.g. '6h', '3h', 'daily'."""
        ...

    @abstractmethod
    async def fetch(self) -> ProviderResult:
        """
        Fetch and return raw observations.
        Must NEVER raise — all errors are returned in ProviderResult.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Quick connectivity check for the source."""
        ...
