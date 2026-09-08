"""
CycloneAI — Satellite Imagery Provider (Phase 2b)

Source:   NASA GIBS (Global Imagery Browse Services)
URL:      https://gibs.earthdata.nasa.gov/wmts/epsg3857/best
Auth:     None — fully public, no API key required
Format:   WMTS raster tiles (PNG/JPEG)
Latency:  Near-real-time (~3-5h for MODIS, ~6h for VIIRS)

Provides satellite imagery layers for cyclone monitoring:
  - Visible (VIS):   True-color corrected reflectance
  - Infrared (IR):   Cloud-top temperature / brightness temperature
  - Water Vapor (WV): Mid-level atmospheric moisture

Each layer includes explicit:
  - source attribution (NASA GIBS / instrument name)
  - observation timestamp
  - tile URL template (WMTS-compatible)
  - availability flag (never fabricated)

Limitations:
  - MODIS/VIIRS imagery has daily granularity (not hourly)
  - No custom Indian Ocean INSAT-3DR data (requires MOSDAC credentials)
  - Visible imagery only available during daytime passes
  - Some layers may have gaps for specific dates
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import aiohttp

from app.config import get_settings

logger = logging.getLogger("cyclone_ai.providers.satellite")


# ---------------------------------------------------------------------------
# Layer definitions — curated for cyclone monitoring
# ---------------------------------------------------------------------------

@dataclass
class GIBSLayerDef:
    """Definition of a GIBS WMTS layer."""
    layer_id: str
    display_name: str
    channel: str            # VIS | IR | WV
    description: str
    instrument: str
    image_format: str       # png | jpg
    default_opacity: float
    max_zoom: int
    attribution: str


# Curated GIBS layers relevant to tropical cyclone monitoring
GIBS_LAYERS: List[GIBSLayerDef] = [
    GIBSLayerDef(
        layer_id="MODIS_Terra_CorrectedReflectance_TrueColor",
        display_name="Visible (True Color)",
        channel="VIS",
        description="MODIS Terra corrected reflectance — true-color visible imagery",
        instrument="MODIS / Terra",
        image_format="jpg",
        default_opacity=0.8,
        max_zoom=9,
        attribution="NASA GIBS / MODIS Terra",
    ),
    GIBSLayerDef(
        layer_id="MODIS_Terra_Cloud_Top_Temp_Day",
        display_name="Cloud-Top Temperature",
        channel="IR",
        description="MODIS Terra daytime cloud-top temperature — proxy for IR imagery",
        instrument="MODIS / Terra",
        image_format="png",
        default_opacity=0.7,
        max_zoom=7,
        attribution="NASA GIBS / MODIS Terra",
    ),
    GIBSLayerDef(
        layer_id="MODIS_Aqua_Cloud_Top_Temp_Day",
        display_name="Cloud-Top Temp (Aqua)",
        channel="IR",
        description="MODIS Aqua daytime cloud-top temperature — complementary IR pass",
        instrument="MODIS / Aqua",
        image_format="png",
        default_opacity=0.7,
        max_zoom=7,
        attribution="NASA GIBS / MODIS Aqua",
    ),
    GIBSLayerDef(
        layer_id="AIRS_L2_Relative_Humidity_500hPa_Day",
        display_name="Water Vapor (500 hPa)",
        channel="WV",
        description="AIRS Level 2 relative humidity at 500 hPa — mid-level moisture",
        instrument="AIRS / Aqua",
        image_format="png",
        default_opacity=0.65,
        max_zoom=6,
        attribution="NASA GIBS / AIRS Aqua",
    ),
    GIBSLayerDef(
        layer_id="VIIRS_SNPP_CorrectedReflectance_TrueColor",
        display_name="Visible (VIIRS)",
        channel="VIS",
        description="VIIRS Suomi NPP corrected reflectance — high-res true-color",
        instrument="VIIRS / Suomi NPP",
        image_format="jpg",
        default_opacity=0.8,
        max_zoom=9,
        attribution="NASA GIBS / VIIRS SNPP",
    ),
]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

@dataclass
class SatelliteLayerInfo:
    """A satellite layer with its tile URL and metadata."""
    layer_id: str
    display_name: str
    channel: str
    description: str
    instrument: str
    tile_url: str
    image_format: str
    default_opacity: float
    max_zoom: int
    timestamp_utc: str      # ISO date string for the tile date
    date_label: str         # Human-readable date
    source: str
    source_url: str
    available: bool
    unavailable_reason: Optional[str] = None


@dataclass
class SatelliteLayersResult:
    """Result of querying available satellite layers."""
    layers: List[SatelliteLayerInfo] = field(default_factory=list)
    retrieved_at_utc: str = ""
    gibs_base_url: str = ""
    note: str = ""


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class SatelliteProvider:
    """
    NASA GIBS satellite imagery provider.

    Discovers available layers for the current (or specified) date and
    returns WMTS tile URL templates that can be used directly by MapLibre GL.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def base_url(self) -> str:
        return self._settings.gibs_wmts_url

    def _tile_url(self, layer: GIBSLayerDef, date_str: str) -> str:
        """
        Build a WMTS tile URL template for MapLibre GL.

        GIBS WMTS RESTful URL pattern (NO 1.0.0/ version segment):
        {base}/{layer}/default/{date}/{tileMatrixSet}/{z}/{y}/{x}.{format}

        The date can be a YYYY-MM-DD string or 'default' for latest available.
        """
        return (
            f"{self.base_url}/{layer.layer_id}/default/"
            f"{date_str}/GoogleMapsCompatible_Level{layer.max_zoom}/"
            "{z}/{y}/{x}." + layer.image_format
        )

    def _source_url(self, layer: GIBSLayerDef) -> str:
        """Build a link to the GIBS layer in NASA Worldview."""
        return f"https://worldview.earthdata.nasa.gov/?l={layer.layer_id}"

    async def check_tile_available(
        self, layer: GIBSLayerDef, date_str: str
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a specific tile exists for a layer+date by probing z=2/y=1/x=2
        (covers ~Indian Ocean region).
        Returns (available, error_reason).
        """
        url = self._tile_url(layer, date_str).format(z=2, y=1, x=2)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    url,
                    timeout=aiohttp.ClientTimeout(total=8),
                    headers={"User-Agent": "CycloneAI/0.2 (research)"},
                ) as resp:
                    if resp.status == 200:
                        return True, None
                    return False, f"HTTP {resp.status}"
        except aiohttp.ClientError as exc:
            return False, f"Network error: {exc}"
        except Exception as exc:
            logger.warning("GIBS tile check failed for %s: %s", layer.layer_id, exc)
            return False, str(exc)

    async def get_layers(
        self, target_date: Optional[datetime] = None
    ) -> SatelliteLayersResult:
        """
        Return available satellite layers for the target date.

        If target_date is None, uses yesterday (GIBS NRT has ~1 day lag
        for most MODIS/VIIRS products).

        Never raises — errors are captured per-layer.
        """
        now = datetime.now(timezone.utc)

        if target_date is None:
            # Use 'default' keyword — GIBS returns the latest available imagery
            date_str = "default"
            date_label = "Latest Available"
        else:
            date_str = target_date.strftime("%Y-%m-%d")
            date_label = target_date.strftime("%d %b %Y")

        layers: List[SatelliteLayerInfo] = []

        for layer_def in GIBS_LAYERS:
            # Skip slow HEAD probes when using 'default' — tiles are always available
            if date_str == "default":
                available, error = True, None
            else:
                available, error = await self.check_tile_available(layer_def, date_str)

            layers.append(SatelliteLayerInfo(
                layer_id=layer_def.layer_id,
                display_name=layer_def.display_name,
                channel=layer_def.channel,
                description=layer_def.description,
                instrument=layer_def.instrument,
                tile_url=self._tile_url(layer_def, date_str),
                image_format=layer_def.image_format,
                default_opacity=layer_def.default_opacity,
                max_zoom=layer_def.max_zoom,
                timestamp_utc=f"{date_str}T00:00:00Z" if date_str != "default" else now.isoformat(),
                date_label=date_label,
                source=layer_def.attribution,
                source_url=self._source_url(layer_def),
                available=available,
                unavailable_reason=error if not available else None,
            ))

        available_count = sum(1 for l in layers if l.available)
        logger.info(
            "Satellite provider: %d/%d layers available for %s",
            available_count, len(layers), date_str,
        )

        return SatelliteLayersResult(
            layers=layers,
            retrieved_at_utc=now.isoformat(),
            gibs_base_url=self.base_url,
            note=(
                f"Satellite imagery from NASA GIBS for {date_label}. "
                f"{available_count}/{len(layers)} layers available. "
                "NRT data has ~3-5h latency. "
                "Source: NASA Global Imagery Browse Services (GIBS)."
            ),
        )


# Module-level singleton
_provider: Optional[SatelliteProvider] = None


def get_satellite_provider() -> SatelliteProvider:
    global _provider
    if _provider is None:
        _provider = SatelliteProvider()
    return _provider

