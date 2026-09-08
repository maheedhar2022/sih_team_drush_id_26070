"""
CycloneAI — RSMC New Delhi Bulletin Provider (stub)

Status: DISABLED by default (RSMC_BULLETIN_ENABLED=false)

Source:   RSMC New Delhi — rsmcnewdelhi.imd.gov.in
Format:   Text bulletins (semi-structured, essay-style)
Auth:     None required
Update:   3-hourly during active storm, daily TWO otherwise

Limitations (documented honestly):
  - No REST API — requires HTML scraping + regex parsing
  - Bulletin format can change between seasons without notice
  - Forecast track only available during active storms
  - No machine-readable history (only current bulletins online)
  - Parsing is fragile — test against real bulletins before enabling

To enable: set RSMC_BULLETIN_ENABLED=true in .env
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings
from app.providers.base import (
    CycloneDataProvider,
    ProviderResult,
    ProviderStatus,
    RawForecastPoint,
    RawObservation,
)

logger = logging.getLogger("cyclone_ai.providers.rsmc_bulletin")

_SOURCE_URL = "https://rsmcnewdelhi.imd.gov.in"
_SOURCE = "RSMC New Delhi / IMD Bulletin (scraped)"


class RSMCBulletinProvider(CycloneDataProvider):
    """
    RSMC New Delhi bulletin scraper.
    Disabled by default. Enable with RSMC_BULLETIN_ENABLED=true.

    Parses text from the RSMC website using regex patterns derived from
    the standard RSMC Tropical Weather Outlook format.
    """

    @property
    def name(self) -> str:
        return "rsmc_bulletin"

    @property
    def display_name(self) -> str:
        return "RSMC New Delhi Bulletin (IMD)"

    @property
    def source_url(self) -> Optional[str]:
        return _SOURCE_URL

    @property
    def update_frequency(self) -> str:
        return "3h"

    async def is_available(self) -> bool:
        settings = get_settings()
        if not settings.rsmc_bulletin_enabled:
            return False
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    _SOURCE_URL, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return resp.status in (200, 301, 302)
        except Exception:
            return False

    async def fetch(self) -> ProviderResult:
        settings = get_settings()
        if not settings.rsmc_bulletin_enabled:
            return ProviderResult(
                provider_name=self.name,
                status=ProviderStatus.DISABLED,
                error_message=(
                    "RSMC bulletin scraper is disabled. "
                    "Set RSMC_BULLETIN_ENABLED=true to enable."
                ),
                source_url=_SOURCE_URL,
            )

        try:
            import aiohttp
            from bs4 import BeautifulSoup

            received_at = datetime.now(timezone.utc)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    _SOURCE_URL,
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers={"User-Agent": "CycloneAI/0.2 (research)"},
                ) as resp:
                    if resp.status != 200:
                        return ProviderResult(
                            provider_name=self.name,
                            status=ProviderStatus.ERROR,
                            error_message=f"HTTP {resp.status}",
                            source_url=_SOURCE_URL,
                        )
                    html = await resp.text(errors="replace")

            observations, forecasts = self._parse_bulletin(html, received_at)
            return ProviderResult(
                provider_name=self.name,
                status=ProviderStatus.OK,
                observations=observations,
                forecasts=forecasts,
                source_url=_SOURCE_URL,
            )

        except ImportError:
            return ProviderResult(
                provider_name=self.name,
                status=ProviderStatus.ERROR,
                error_message="beautifulsoup4/lxml not installed.",
                source_url=_SOURCE_URL,
            )
        except Exception as exc:
            logger.exception("RSMC bulletin fetch error: %s", exc)
            return ProviderResult(
                provider_name=self.name,
                status=ProviderStatus.ERROR,
                error_message=str(exc),
                source_url=_SOURCE_URL,
            )

    def _parse_bulletin(
        self, html: str, received_at: datetime
    ) -> tuple[list[RawObservation], list[RawForecastPoint]]:
        """
        Parse RSMC bulletin HTML.
        Returns empty lists if no active storm is found.

        Regex patterns derived from RSMC Tropical Weather Outlook SOP.
        These are conservative and will miss data rather than produce
        wrong data (fail-safe).
        """
        from bs4 import BeautifulSoup

        observations: list[RawObservation] = []
        forecasts: list[RawForecastPoint] = []

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(separator="\n")

        # Check for active storm
        if not re.search(
            r"(cyclonic storm|depression|cyclone warning|tropical weather)",
            text, re.IGNORECASE
        ):
            logger.info("RSMC bulletin: no active NI storm detected")
            return observations, forecasts

        # Extract position pattern: "centred near latitude X.X°N and longitude Y.Y°E"
        pos_match = re.search(
            r"(?:centred|center(?:ed)?)\s+near\s+latitude\s+"
            r"(\d+\.?\d*)\s*[°\u00b0]?\s*N\s*(?:and)?\s*longitude\s+"
            r"(\d+\.?\d*)\s*[°\u00b0]?\s*E",
            text, re.IGNORECASE
        )

        if pos_match:
            lat = float(pos_match.group(1))
            lon = float(pos_match.group(2))

            # Extract wind: "maximum sustained wind speed of XX knots"
            wind_match = re.search(
                r"maximum\s+sustained\s+wind\s+speed\s+of\s+(\d+)\s*(?:knot|kt)",
                text, re.IGNORECASE
            )
            wind_kt = float(wind_match.group(1)) if wind_match else None

            # Extract pressure: "central pressure of XXX hPa"
            pres_match = re.search(
                r"central\s+pressure\s+of\s+(\d{3,4})\s*(?:hPa|mb)",
                text, re.IGNORECASE
            )
            pressure = float(pres_match.group(1)) if pres_match else None

            # Extract storm name
            name_match = re.search(
                r"(?:cyclone|storm|depression)\s+([A-Z][A-Z]+)",
                text, re.IGNORECASE
            )
            name = name_match.group(1).upper() if name_match else "UNNAMED"

            obs = RawObservation(
                cyclone_id=f"NI_{name}_{received_at.year}",
                cyclone_name=name,
                basin="NI",
                timestamp_utc=received_at,
                latitude=lat,
                longitude=lon,
                wind_speed=wind_kt,
                wind_unit="kt",
                central_pressure=pressure,
                intensity_category=None,  # derive during normalisation
                movement_direction=None,
                movement_speed=None,
                source=_SOURCE,
                source_url=_SOURCE_URL,
                received_at_utc=received_at,
                raw_data=text[:1000],
            )
            observations.append(obs)
            logger.info(
                "RSMC bulletin: parsed storm %s at %.2fN %.2fE", name, lat, lon
            )

        return observations, forecasts
