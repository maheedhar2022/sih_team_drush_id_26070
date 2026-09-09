"""
CycloneAI — Historical Provider (Phase 2)

Wraps the verified IMD/RSMC historical dataset from demo_data.py.
This is the fallback when no active NI storms are present in IBTrACS.

Source:   IMD/RSMC New Delhi Best Track (IBTrACS 2020136N10088)
Dataset:  AMPHAN 2020 — verified 14-point track
DataMode: HISTORICAL (not DEMO — it is real, verified data, just not current)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.providers.base import (
    CycloneDataProvider,
    ProviderResult,
    ProviderStatus,
    RawObservation,
)
from app.services.demo_data import AMPHAN_IBTRACS_SID, _AMPHAN_TRACK_RAW

logger = logging.getLogger("cyclone_ai.providers.historical")

_SOURCE = "IMD/RSMC New Delhi Best Track (IBTrACS 2020136N10088)"
_SOURCE_URL = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/"


class HistoricalProvider(CycloneDataProvider):
    """
    Returns the verified historical AMPHAN 2020 dataset.
    Used as fallback when no active NI storms are present.
    """

    @property
    def name(self) -> str:
        return "historical"

    @property
    def display_name(self) -> str:
        return "IMD/RSMC Historical Dataset (AMPHAN 2020)"

    @property
    def source_url(self) -> Optional[str]:
        return _SOURCE_URL

    @property
    def update_frequency(self) -> str:
        return "static"

    async def is_available(self) -> bool:
        return True  # always available (local data)

    async def fetch(self) -> ProviderResult:
        received_at = datetime.now(timezone.utc)
        observations = []

        for raw in _AMPHAN_TRACK_RAW:
            ts = datetime.fromisoformat(raw["ts"].replace("Z", "+00:00"))
            obs = RawObservation(
                cyclone_id=AMPHAN_IBTRACS_SID,
                cyclone_name="AMPHAN",
                basin="NI",
                timestamp_utc=ts,
                latitude=raw["lat"],
                longitude=raw["lon"],
                wind_speed=raw["wind"] / 1.852,  # km/h → kt for normalisation
                wind_unit="kt",
                central_pressure=float(raw["pres"]),
                intensity_category=raw["cat"],
                movement_direction="NNW",
                movement_speed=None,
                source=_SOURCE,
                source_url=_SOURCE_URL,
                received_at_utc=received_at,
                raw_data=str(raw),
            )
            observations.append(obs)

        logger.info("HistoricalProvider: returned %d AMPHAN 2020 observations", len(observations))
        return ProviderResult(
            provider_name=self.name,
            status=ProviderStatus.OK,
            observations=observations,
            fetched_at_utc=received_at,
            source_url=_SOURCE_URL,
        )
