"""
CycloneAI — Data Provider Registry (Phase 2)

Selects and orchestrates providers based on configuration.
Provider priority for NI basin:
  1. IBTracsProvider  (primary — public, updated 6-hourly)
  2. RSMCBulletinProvider (optional — when RSMC_BULLETIN_ENABLED=true)
  3. HistoricalProvider  (fallback — when no active NI storms)

Rules:
  - If IBTrACS returns active NI storms → use them (DataMode.LIVE/DELAYED)
  - If IBTrACS succeeds but no active NI storms → use HistoricalProvider
    with DataMode.HISTORICAL and explicit label
  - If IBTrACS fails → show DATA_SOURCE_UNAVAILABLE + last valid DB record
    (never silently substitute demo data)
"""
from __future__ import annotations

import logging
from typing import List, Optional

from app.providers.base import CycloneDataProvider, ProviderResult, ProviderStatus
from app.providers.historical import HistoricalProvider
from app.providers.ibtracs import IBTracsProvider
from app.providers.rsmc_bulletin import RSMCBulletinProvider

logger = logging.getLogger("cyclone_ai.providers.registry")


class DataProviderRegistry:
    """
    Singleton registry that manages all data providers.
    Access via `get_registry()`.
    """

    def __init__(self) -> None:
        self._ibtracs = IBTracsProvider()
        self._rsmc = RSMCBulletinProvider()
        self._historical = HistoricalProvider()

        self._last_results: dict[str, ProviderResult] = {}

    @property
    def providers(self) -> List[CycloneDataProvider]:
        return [self._ibtracs, self._rsmc, self._historical]

    @property
    def ibtracs(self) -> IBTracsProvider:
        return self._ibtracs

    @property
    def rsmc(self) -> RSMCBulletinProvider:
        return self._rsmc

    @property
    def historical(self) -> HistoricalProvider:
        return self._historical

    async def fetch_all(self) -> List[ProviderResult]:
        """
        Fetch from all enabled providers.
        Returns results in priority order.
        """
        results: List[ProviderResult] = []

        # 1. IBTrACS (primary)
        logger.info("Fetching from IBTrACS provider...")
        ibtracs_result = await self._ibtracs.fetch()
        results.append(ibtracs_result)
        self._last_results["ibtracs"] = ibtracs_result

        # 2. RSMC bulletin (optional)
        rsmc_result = await self._rsmc.fetch()
        results.append(rsmc_result)
        self._last_results["rsmc_bulletin"] = rsmc_result

        # 3. Historical (always available — used as fallback by ingestion)
        historical_result = await self._historical.fetch()
        results.append(historical_result)
        self._last_results["historical"] = historical_result

        return results

    def get_last_result(self, provider_name: str) -> Optional[ProviderResult]:
        return self._last_results.get(provider_name)

    def get_provider_statuses(self) -> dict[str, str]:
        """Return status dict for health endpoint."""
        return {
            name: result.status.value
            for name, result in self._last_results.items()
        }


# Module-level singleton
_registry: Optional[DataProviderRegistry] = None


def get_registry() -> DataProviderRegistry:
    global _registry
    if _registry is None:
        _registry = DataProviderRegistry()
    return _registry
