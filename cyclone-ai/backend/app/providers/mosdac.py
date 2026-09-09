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
import hashlib
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
    observation_start_utc: Optional[datetime] = None
    observation_end_utc: Optional[datetime] = None
    bbox_north: Optional[float] = None
    bbox_south: Optional[float] = None
    bbox_east: Optional[float] = None
    bbox_west: Optional[float] = None


@dataclass
class MOSDACAuthToken:
    """Authentication tokens from MOSDAC."""
    access_token: str
    refresh_token: str
    username: str


@dataclass
class MOSDACDownloadResult:
    """A completed source-product download and its integrity metadata."""
    path: Path
    checksum_sha256: str
    byte_count: int


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

    @staticmethod
    def _parse_source_datetime(value: object) -> Optional[datetime]:
        if not isinstance(value, str) or not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            return None

    @classmethod
    def _parse_dc_date(cls, value: object) -> tuple[Optional[datetime], Optional[datetime]]:
        if not isinstance(value, str) or not value:
            return None, None
        start, _, end = value.partition("/")
        return cls._parse_source_datetime(start), cls._parse_source_datetime(end)

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
                    timeout=aiohttp.ClientTimeout(total=self._settings.mosdac_request_timeout_seconds),
                ) as resp:
                    if resp.status == 401:
                        body = await resp.json()
                        err = body.get("error", "Invalid credentials")
                        logger.error("MOSDAC auth failed (401): %s", err)
                        return None

                    if resp.status != 200:
                        logger.error("MOSDAC auth failed: HTTP %d", resp.status)
                        return None

                    body = await resp.json(content_type=None)
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
                    timeout=aiohttp.ClientTimeout(total=self._settings.mosdac_request_timeout_seconds),
                    headers={"User-Agent": "CycloneAI/0.3 (research)"},
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
                        observed_at, observation_end = self._parse_dc_date(item.get("dcDate"))
                        bbox = (item.get("boundbox") or [{}])[0]
                        entries.append(MOSDACSearchResult(
                            record_id=item.get("id", ""),
                            identifier=item.get("identifier", ""),
                            updated=item.get("updated", ""),
                            dataset_id=dataset_id,
                            observation_start_utc=observed_at,
                            observation_end_utc=observation_end,
                            bbox_north=self._parse_float(bbox.get("north")),
                            bbox_south=self._parse_float(bbox.get("south")),
                            bbox_east=self._parse_float(bbox.get("east")),
                            bbox_west=self._parse_float(bbox.get("west")),
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

    @staticmethod
    def _parse_float(value: object) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    async def discover_products(
        self, target_date: Optional[datetime] = None, count: int = 5,
    ) -> tuple[str, List[MOSDACSearchResult]]:
        """Discover exact source granules, preferring INSAT-3DS over INSAT-3DR."""
        # MOSDAC publishes new INSAT granules through the current UTC day.  The
        # scheduler should therefore discover the live catalog window by default.
        target_date = target_date or datetime.now(timezone.utc)
        start_date = target_date.strftime("%Y-%m-%d")
        end_date = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")

        for dataset_id in MOSDAC_DATASETS:
            _, entries = await self.search_dataset(dataset_id, start_date, end_date, count=count)
            valid_entries = [entry for entry in entries if entry.record_id and entry.identifier]
            if valid_entries:
                return dataset_id, valid_entries
        return "", []

    async def logout(self) -> None:
        """End an authenticated MOSDAC session without logging token material."""
        if self._token is None:
            return
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    MOSDAC_LOGOUT_URL,
                    headers={"Authorization": f"Bearer {self._token.access_token}"},
                    timeout=aiohttp.ClientTimeout(total=self._settings.mosdac_request_timeout_seconds),
                )
        except aiohttp.ClientError as exc:
            logger.warning("MOSDAC logout failed: %s", exc)
        finally:
            self._token = None

    async def download_record(self, record_id: str, destination: Path) -> MOSDACDownloadResult:
        """Download one authenticated source granule to a caller-controlled path."""
        token = await self.authenticate()
        if token is None:
            raise RuntimeError("MOSDAC authentication failed; source product was not downloaded.")

        temporary_path = destination.with_suffix(destination.suffix + ".part")
        maximum_bytes = self._settings.satellite_max_download_mb * 1024 * 1024
        checksum = hashlib.sha256()
        byte_count = 0

        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    MOSDAC_DOWNLOAD_URL,
                    params={"id": record_id},
                    headers={"Authorization": f"Bearer {token.access_token}"},
                    timeout=aiohttp.ClientTimeout(total=self._settings.mosdac_request_timeout_seconds),
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"MOSDAC download returned HTTP {response.status}.")
                    declared_size = response.content_length
                    if declared_size is not None and declared_size > maximum_bytes:
                        raise RuntimeError("MOSDAC source product exceeds SATELLITE_MAX_DOWNLOAD_MB.")
                    with temporary_path.open("wb") as output:
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            byte_count += len(chunk)
                            if byte_count > maximum_bytes:
                                raise RuntimeError("MOSDAC source product exceeds SATELLITE_MAX_DOWNLOAD_MB.")
                            checksum.update(chunk)
                            output.write(chunk)
            os.replace(temporary_path, destination)
            return MOSDACDownloadResult(destination, checksum.hexdigest(), byte_count)
        except aiohttp.ClientError as exc:
            raise RuntimeError(f"MOSDAC download network error: {exc}") from exc
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
            await self.logout()

    async def get_layers(
        self, target_date: Optional[datetime] = None
    ) -> MOSDACLayersResult:
        """
        Check available MOSDAC/INSAT satellite data for the target date.

        Returns metadata about available imagery — does NOT download files.
        This is used to populate the frontend satellite layer panel alongside
        NASA GIBS layers.
        """
        now = datetime.now(timezone.utc)
        dataset_id, entries = await self.discover_products(target_date=target_date, count=2)
        product_label = MOSDAC_DATASETS[dataset_id]["satellite"] if dataset_id else "INSAT"
        logger.info("MOSDAC provider: %d source granules discovered for %s", len(entries), product_label)

        # A discovered HDF product is not a web overlay. The catalog/download
        # pipeline records it separately; only a format-validated processed
        # asset can be exposed to MapLibre later.
        return MOSDACLayersResult(
            layers=[],
            retrieved_at_utc=now.isoformat(),
            authenticated=False,
            note=(
                f"MOSDAC/ISRO discovered {len(entries)} {product_label} source granule(s). "
                "No INSAT map layer is exposed until source-product validation and processing complete."
            ),
        )


# Module-level singleton
_provider: Optional[MOSDACProvider] = None


def get_mosdac_provider() -> MOSDACProvider:
    global _provider
    if _provider is None:
        _provider = MOSDACProvider()
    return _provider
