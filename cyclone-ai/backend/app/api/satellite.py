"""
CycloneAI — Satellite Imagery API Router (Phase 2b)

Endpoints:
  GET /api/satellite/layers         — List available satellite imagery layers
  GET /api/satellite/tile/{...}     — Proxy tile request to NASA GIBS

All responses include explicit source attribution.
No tiles are fabricated — unavailable layers return clear status.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

import aiohttp
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import get_settings
from app.providers.satellite import get_satellite_provider
from app.providers.mosdac import get_mosdac_provider
from app.services.satellite_catalog import (
    SatelliteStorage,
    available_channels,
    catalog_summary,
    get_observation,
    list_observations,
    observation_payload,
)

logger = logging.getLogger("cyclone_ai.api.satellite")
router = APIRouter(prefix="/api/satellite", tags=["satellite"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class SatelliteLayerResponse(BaseModel):
    layer_id: str
    display_name: str
    channel: str            # VIS | IR | WV
    description: str
    instrument: str
    tile_url: str
    image_format: str
    default_opacity: float
    max_zoom: int
    timestamp_utc: str
    date_label: str
    source: str
    source_url: str
    available: bool
    unavailable_reason: Optional[str] = None


class SatelliteLayersListResponse(BaseModel):
    layers: List[SatelliteLayerResponse]
    retrieved_at_utc: str
    gibs_base_url: str
    note: str


class SatelliteObservationResponse(BaseModel):
    id: int
    source: str
    source_record_id: str
    satellite: str
    sensor: Optional[str] = None
    product_id: str
    product_name: Optional[str] = None
    channel: Optional[str] = None
    processing_level: Optional[str] = None
    observation_timestamp_utc: Optional[datetime] = None
    received_at_utc: datetime
    processed_at_utc: Optional[datetime] = None
    bbox: Optional[dict[str, float]] = None
    projection: Optional[str] = None
    spatial_resolution_m: Optional[float] = None
    file_format: Optional[str] = None
    source_url: Optional[str] = None
    checksum_sha256: Optional[str] = None
    status: str
    failure_reason: Optional[str] = None
    web_image_available: bool


class SatelliteObservationListResponse(BaseModel):
    observations: List[SatelliteObservationResponse]
    count: int


class SatelliteCatalogStatusResponse(BaseModel):
    satellite_enabled: bool
    mosdac_enabled: bool
    mosdac_configured: bool
    storage_root_configured: bool
    latest_observation_utc: Optional[datetime] = None
    catalog_state: str
    note: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/layers",
    response_model=SatelliteLayersListResponse,
    summary="List available satellite imagery layers",
)
async def list_satellite_layers(
    date: Optional[str] = Query(
        None,
        description="Target date (YYYY-MM-DD). Defaults to yesterday (NRT).",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    ),
) -> SatelliteLayersListResponse:
    """
    Returns available satellite imagery layers with tile URL templates.

    Each layer includes:
    - WMTS tile URL template (for MapLibre GL)
    - Observation timestamp
    - Source attribution
    - Availability status

    Tile URL templates use {z}/{y}/{x} placeholders compatible with
    MapLibre GL raster sources.
    """
    settings = get_settings()

    if not settings.satellite_enabled:
        return SatelliteLayersListResponse(
            layers=[],
            retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
            gibs_base_url="",
            note="Satellite imagery is disabled in configuration.",
        )

    provider = get_satellite_provider()

    # Parse date if provided
    target_date = None
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date format: '{date}'. Expected YYYY-MM-DD.",
            )

    result = await provider.get_layers(target_date=target_date)

    gibs_layers = [
        SatelliteLayerResponse(
            layer_id=l.layer_id,
            display_name=l.display_name,
            channel=l.channel,
            description=l.description,
            instrument=l.instrument,
            tile_url=l.tile_url,
            image_format=l.image_format,
            default_opacity=l.default_opacity,
            max_zoom=l.max_zoom,
            timestamp_utc=l.timestamp_utc,
            date_label=l.date_label,
            source=l.source,
            source_url=l.source_url,
            available=l.available,
            unavailable_reason=l.unavailable_reason,
        )
        for l in result.layers
    ]

    # Also fetch MOSDAC layers (non-blocking — don't fail if MOSDAC is slow)
    mosdac_layers: list[SatelliteLayerResponse] = []
    mosdac_note = ""
    try:
        mosdac = get_mosdac_provider()
        if settings.mosdac_enabled and mosdac.is_configured:
            mosdac_result = await mosdac.get_layers(target_date=target_date)
            mosdac_note = f" | {mosdac_result.note}"
            for ml in mosdac_result.layers:
                mosdac_layers.append(SatelliteLayerResponse(
                    layer_id=ml.layer_id,
                    display_name=ml.display_name,
                    channel=ml.channel,
                    description=ml.description,
                    instrument=ml.satellite,
                    tile_url="",  # MOSDAC doesn't serve tiles
                    image_format="hdf5",
                    default_opacity=0.7,
                    max_zoom=6,
                    timestamp_utc=ml.timestamp_utc,
                    date_label=ml.date_label,
                    source=ml.source,
                    source_url=ml.source_url,
                    available=ml.available,
                    unavailable_reason=ml.unavailable_reason,
                ))
        elif mosdac.is_configured:
            mosdac_note = " | MOSDAC: disabled until explicitly enabled"
    except Exception as exc:
        logger.warning("MOSDAC layer fetch failed (non-fatal): %s", exc)
        mosdac_note = " | MOSDAC: unavailable"

    all_layers = gibs_layers + mosdac_layers

    return SatelliteLayersListResponse(
        layers=all_layers,
        retrieved_at_utc=result.retrieved_at_utc,
        gibs_base_url=result.gibs_base_url,
        note=result.note + mosdac_note,
    )


@router.get(
    "/latest",
    response_model=SatelliteLayersListResponse,
    summary="List the latest available satellite imagery layers",
)
async def list_latest_satellite_layers() -> SatelliteLayersListResponse:
    """Return dated, availability-checked layers for the latest NRT observation day."""
    return await list_satellite_layers(date=None)


@router.get(
    "/status",
    response_model=SatelliteCatalogStatusResponse,
    summary="Get INSAT/MOSDAC ingestion catalog status",
)
async def satellite_catalog_status() -> SatelliteCatalogStatusResponse:
    """Report catalog readiness without exposing credentials or source files."""
    return SatelliteCatalogStatusResponse(**await catalog_summary())


@router.get(
    "/observations",
    response_model=SatelliteObservationListResponse,
    summary="List validated satellite source-product catalog entries",
)
async def list_satellite_observations(
    limit: int = Query(50, ge=1, le=200),
    source: Optional[str] = Query(None, max_length=64),
) -> SatelliteObservationListResponse:
    """List discovered/downloaded/processed products with their true state."""
    observations = await list_observations(limit=limit, source=source)
    return SatelliteObservationListResponse(
        observations=[SatelliteObservationResponse(**observation_payload(item)) for item in observations],
        count=len(observations),
    )


@router.get(
    "/channels",
    summary="List channels represented by cataloged satellite observations",
)
async def list_satellite_channels() -> dict:
    return {"channels": await available_channels()}


@router.get(
    "/observations/{observation_id}/image",
    summary="Return a processed satellite image when one has been validated",
    responses={404: {"description": "No processed image is available"}},
)
async def get_satellite_observation_image(observation_id: int) -> FileResponse:
    observation = await get_observation(observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="Satellite observation not found.")
    if observation.status != "PROCESSED" or not observation.web_asset_path:
        raise HTTPException(
            status_code=404,
            detail="No validated web image is available for this source product.",
        )

    try:
        asset_path = SatelliteStorage.from_settings().resolve_existing(observation.web_asset_path)
    except ValueError:
        logger.error("Rejected unsafe satellite asset path for observation %s", observation_id)
        raise HTTPException(status_code=500, detail="Stored satellite asset path is invalid.")

    if not asset_path.is_file():
        raise HTTPException(status_code=404, detail="Processed satellite image file is unavailable.")

    media_type = "image/png" if asset_path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(asset_path, media_type=media_type, filename=asset_path.name)


@router.get(
    "/observations/{observation_id}",
    response_model=SatelliteObservationResponse,
    summary="Get source and processing metadata for one satellite observation",
)
async def get_satellite_observation(observation_id: int) -> SatelliteObservationResponse:
    observation = await get_observation(observation_id)
    if observation is None:
        raise HTTPException(status_code=404, detail="Satellite observation not found.")
    return SatelliteObservationResponse(**observation_payload(observation))


@router.get(
    "/tile/{layer_id}/{z}/{y}/{x}",
    summary="Proxy a satellite tile from NASA GIBS",
    responses={
        200: {"content": {"image/png": {}, "image/jpeg": {}}},
        404: {"description": "Tile not found"},
        502: {"description": "Upstream GIBS error"},
    },
)
async def proxy_satellite_tile(
    layer_id: str,
    z: int,
    y: int,
    x: int,
    date: Optional[str] = Query(
        None,
        description="Tile date (YYYY-MM-DD). Defaults to yesterday.",
    ),
) -> Response:
    """
    Proxies a single tile request to NASA GIBS WMTS.

    This proxy allows the frontend to avoid CORS issues and enables
    server-side caching headers. The tile is returned as-is from GIBS.
    """
    settings = get_settings()

    if not settings.satellite_enabled:
        raise HTTPException(status_code=503, detail="Satellite imagery disabled.")

    from app.providers.satellite import GIBS_LAYERS

    # Find the layer definition
    layer_def = None
    for ld in GIBS_LAYERS:
        if ld.layer_id == layer_id:
            layer_def = ld
            break

    if layer_def is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown layer: '{layer_id}'",
        )

    # Determine date
    from datetime import timedelta
    if date:
        date_str = date
    else:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")

    # Build the upstream GIBS URL
    gibs_url = (
        f"{settings.gibs_wmts_url}/{layer_id}/default/"
        f"{date_str}/GoogleMapsCompatible_Level{layer_def.max_zoom}/"
        f"{z}/{y}/{x}.{layer_def.image_format}"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                gibs_url,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "CycloneAI/0.2 (research)"},
            ) as resp:
                if resp.status != 200:
                    raise HTTPException(
                        status_code=resp.status if resp.status == 404 else 502,
                        detail=f"GIBS returned HTTP {resp.status} for {layer_id}",
                    )

                content = await resp.read()
                content_type = (
                    "image/jpeg"
                    if layer_def.image_format == "jpg"
                    else "image/png"
                )

                return Response(
                    content=content,
                    media_type=content_type,
                    headers={
                        "Cache-Control": f"public, max-age={settings.gibs_tile_cache_seconds}",
                        "X-Source": "NASA GIBS",
                        "X-Layer": layer_id,
                        "X-Date": date_str,
                    },
                )

    except aiohttp.ClientError as exc:
        logger.error("GIBS tile proxy error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch tile from GIBS: {exc}",
        )
