"""
CycloneAI — MOSDAC/ISRO INSAT-3DR Provider (Phase 2b)

Source:   MOSDAC (Meteorological & Oceanographic Satellite Data Archival Centre)
URL:      https://mosdac.gov.in
Auth:     Registered account (username/password → Bearer token)
Satellite: INSAT-3DR / INSAT-3DS (Indian geostationary)
Coverage:  Indian Ocean region (40°E–120°E, 40°S–40°N)

API Endpoints (discovered from official mdapi.py tool):
  - Search:   GET  https://mosdac.gov.in/apios/datasets.json
  - Token:    POST https://mosdac.gov.in/download_api/gettoken
  - Download: GET  https://mosdac.gov.in/download_api/download
  - Logout:   POST https://mosdac.gov.in/download_api/logout

Dataset IDs for satellite imagery:
  - 3SIMG_L1B_STD: INSAT-3DS Imager L1B Standard (current operational)
  - 3RIMG_L1B_STD: INSAT-3DR Imager L1B Standard
  - 3DIMG_L1B_STD: INSAT-3D Imager L1B Standard (legacy)

Channels available in L1B Standard products:
  - VIS  (0.55-0.75 μm)  : Visible
  - SWIR (1.55-1.70 μm)  : Short-wave IR
  - MIR  (3.80-4.00 μm)  : Mid-wave IR
  - WV   (6.50-7.10 μm)  : Water Vapor
  - TIR1 (10.3-11.3 μm)  : Thermal IR band 1
  - TIR2 (11.5-12.5 μm)  : Thermal IR band 2

Limitations:
  - MOSDAC server can be very slow (15-60s response times)
  - Data is HDF5/large files, not map tiles
  - Browse images are full-disk geostationary projections (not mercator tiles)
  - Requires authenticated download for actual data files
  - Daily download quota: 5000 files/user
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp

from app.config import get_settings

logger = logging.getLogger("cyclone_ai.providers.mosdac")

# ---------------------------------------------------------------------------
# MOSDAC API endpoints (from official mdapi.py)
# ---------------------------------------------------------------------------
MOSDAC_TOKEN_URL = "https://mosdac.gov.in/download_api/gettoken"
MOSDAC_SEARCH_URL = "https://mosdac.gov.in/apios/datasets.json"
MOSDAC_DOWNLOAD_URL = "https://mosdac.gov.in/download_api/download"
MOSDAC_LOGOUT_URL = "https://mosdac.gov.in/download_api/logout"

# Dataset IDs for INSAT satellites
MOSDAC_DATASETS = {
    "3SIMG_L1B_STD": {
        "satellite": "INSAT-3DS",
        "sensor": "Imager",
        "description": "INSAT-3DS Imager L1B Standard Products",
    },
    "3RIMG_L1B_STD": {
        "satellite": "INSAT-3DR",
        "sensor": "Imager",
        "description": "INSAT-3DR Imager L1B Standard Products",
    },
}

# Channel definitions for INSAT-3DR/3DS Imager
INSAT_CHANNELS = {
    "VIS": {
        "display_name": "Visible (INSAT)",
        "wavelength": "0.55-0.75 μm",
        "description": "Visible channel — daytime cloud patterns",
    },
    "WV": {
        "display_name": "Water Vapor (INSAT)",
        "wavelength": "6.50-7.10 μm",
        "description": "Water vapor channel — mid-level atmospheric moisture",
    },
    "TIR1": {
        "display_name": "Thermal IR (INSAT)",
        "wavelength": "10.3-11.3 μm",
        "description": "Thermal infrared band 1 — cloud-top temperature",
    },
}


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

@dataclass
class MOSDACSearchResult:
    """A single file entry from MOSDAC search API."""
    record_id: str
    identifier: str         # Filename
    updated: str            # ISO timestamp
    dataset_id: str


@dataclass
class MOSDACAuthToken:
    """Authentication tokens from MOSDAC."""
    access_token: str
    refresh_token: str
    username: str


@dataclass
class MOSDACLayerInfo:
    """MOSDAC satellite layer info for frontend."""
    layer_id: str
    display_name: str
    channel: str
    description: str
    satellite: str
    dataset_id: str
    timestamp_utc: str
    date_label: str
    source: str
    source_url: str
    available: bool
    file_count: int
    unavailable_reason: Optional[str] = None
    # If we have a cached browse image
    browse_image_url: Optional[str] = None


@dataclass
class MOSDACLayersResult:
    """Result of querying MOSDAC satellite layers."""
    layers: List[MOSDACLayerInfo] = field(default_factory=list)
    retrieved_at_utc: str = ""
    authenticated: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class MOSDACProvider:
    """
    MOSDAC/ISRO satellite data provider.

    Authenticates with MOSDAC credentials, searches for recent INSAT-3DR/3DS
    imagery, and provides metadata about available satellite products.

    This provider does NOT serve map tiles (MOSDAC data is full-disk HDF5).
    Instead, it provides:
    1. Metadata about available imagery (timestamps, channels, counts)
    2. Authentication for data download if needed
    3. Integration with the MOSDAC download pipeline
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._token: Optional[MOSDACAuthToken] = None
        self._cache_dir = Path(self._settings.mosdac_api_url.replace("https://", "").replace("/", "_"))

    @property
    def is_configured(self) -> bool:
        """Check if MOSDAC credentials are set."""
        return bool(self._settings.mosdac_username and self._settings.mosdac_password)

    async def authenticate(self) -> Optional[MOSDACAuthToken]:
        """
        Authenticate with MOSDAC and get Bearer tokens.
        Returns None if authentication fails.
        """
        if not self.is_configured:
            logger.warning("MOSDAC credentials not configured — skipping auth")
            return None

        data = {
            "username": self._settings.mosdac_username,
            "password": self._settings.mosdac_password,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    MOSDAC_TOKEN_URL,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 401:
                        body = await resp.json()
                        err = body.get("error", "Invalid credentials")
                        logger.error("MOSDAC auth failed (401): %s", err)
                        return None

                    if resp.status != 200:
                        logger.error("MOSDAC auth failed: HTTP %d", resp.status)
                        return None

                    body = await resp.json()
                    self._token = MOSDACAuthToken(
                        access_token=body["access_token"],
                        refresh_token=body["refresh_token"],
                        username=self._settings.mosdac_username,
                    )
                    logger.info("MOSDAC authenticated as %s", self._settings.mosdac_username)
                    return self._token

        except aiohttp.ClientError as exc:
            logger.error("MOSDAC auth network error: %s", exc)
            return None
        except Exception as exc:
            logger.exception("MOSDAC auth unexpected error: %s", exc)
            return None

    async def search_dataset(
        self,
        dataset_id: str,
        start_date: str,
        end_date: str,
        count: int = 5,
    ) -> Tuple[int, List[MOSDACSearchResult]]:
        """
        Search MOSDAC for files matching a dataset and date range.
        The search API is public (no auth needed).

        Returns (total_results, list_of_entries).
        """
        # The official mdapi client accepts at most 100 results per request.
        # Sending a larger value is one documented source of HTTP 400 responses.
        params = {
            "datasetId": dataset_id,
            "startTime": start_date,
            "endTime": end_date,
            "count": str(max(1, min(count, 100))),
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    MOSDAC_SEARCH_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=60),  # MOSDAC is slow
                    headers={"User-Agent": "CycloneAI/0.2 (research)"},
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "MOSDAC search failed for %s: HTTP %d",
                            dataset_id, resp.status,
                        )
                        return 0, []

                    body = await resp.json(content_type=None)
                    total = body.get("totalResults", 0)
                    entries = []

                    for item in body.get("entries", []):
                        entries.append(MOSDACSearchResult(
                            record_id=item.get("id", ""),
                            identifier=item.get("identifier", ""),
                            updated=item.get("updated", ""),
                            dataset_id=dataset_id,
                        ))

                    logger.info(
                        "MOSDAC search: %d files found for %s (%s to %s)",
                        total, dataset_id, start_date, end_date,
                    )
                    return total, entries

        except aiohttp.ClientError as exc:
            logger.error("MOSDAC search network error: %s", exc)
            return 0, []
        except Exception as exc:
            logger.exception("MOSDAC search error: %s", exc)
            return 0, []

    async def get_layers(
        self, target_date: Optional[datetime] = None
    ) -> MOSDACLayersResult:
        """
        Check available MOSDAC/INSAT satellite data for the target date.

        Returns metadata about available imagery — does NOT download files.
        This is used to populate the frontend satellite layer panel alongside
        NASA GIBS layers.
        """
        if not self.is_configured:
            return MOSDACLayersResult(
                retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                authenticated=False,
                note="MOSDAC credentials not configured. Set MOSDAC_USERNAME and MOSDAC_PASSWORD in .env",
            )

        now = datetime.now(timezone.utc)
        if target_date is None:
            target_date = now - timedelta(days=1)

        date_str = target_date.strftime("%Y-%m-%d")
        end_str = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")
        date_label = target_date.strftime("%d %b %Y")

        layers: List[MOSDACLayerInfo] = []

        # Try INSAT-3DS first (current operational), then INSAT-3DR
        for dataset_id, ds_info in MOSDAC_DATASETS.items():
            try:
                total, entries = await self.search_dataset(
                    dataset_id=dataset_id,
                    start_date=date_str,
                    end_date=end_str,
                    count=2,
                )
            except Exception:
                total, entries = 0, []

            for channel_key, ch_info in INSAT_CHANNELS.items():
                layer_id = f"mosdac_{dataset_id}_{channel_key}"

                layers.append(MOSDACLayerInfo(
                    layer_id=layer_id,
                    display_name=f"{ch_info['display_name']} — {ds_info['satellite']}",
                    channel=channel_key if channel_key in ("VIS", "WV") else "IR",
                    description=f"{ch_info['description']} ({ch_info['wavelength']})",
                    satellite=ds_info["satellite"],
                    dataset_id=dataset_id,
                    timestamp_utc=f"{date_str}T00:00:00Z",
                    date_label=date_label,
                    source=f"MOSDAC/ISRO — {ds_info['satellite']}",
                    source_url="https://mosdac.gov.in",
                    available=total > 0,
                    file_count=total,
                    unavailable_reason=None if total > 0 else "No data files found for this date",
                ))

            # If INSAT-3DS has data, skip 3DR (avoid duplicates)
            if total > 0:
                break

        # Try to authenticate (to verify credentials work)
        auth_ok = False
        try:
            token = await self.authenticate()
            auth_ok = token is not None
        except Exception:
            auth_ok = False

        available_count = sum(1 for l in layers if l.available)
        logger.info(
            "MOSDAC provider: %d layers, %d available for %s, auth=%s",
            len(layers), available_count, date_str, auth_ok,
        )

        return MOSDACLayersResult(
            layers=layers,
            retrieved_at_utc=now.isoformat(),
            authenticated=auth_ok,
            note=(
                f"MOSDAC/ISRO satellite data for {date_label}. "
                f"{'Authenticated' if auth_ok else 'Auth failed or pending'}. "
                f"{available_count} channel(s) available. "
                "Source: ISRO MOSDAC — Indian geostationary satellites."
            ),
        )


# Module-level singleton
_provider: Optional[MOSDACProvider] = None


def get_mosdac_provider() -> MOSDACProvider:
    global _provider
    if _provider is None:
        _provider = MOSDACProvider()
    return _provider
