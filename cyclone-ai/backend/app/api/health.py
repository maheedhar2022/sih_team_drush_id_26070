"""
CycloneAI — Health API Router (Phase 2)

GET /api/health
  Returns system status, provider statuses, last ingestion time,
  active NI storm count, demo mode flag, version, and timestamp.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import get_settings
from app.schemas.cyclone import DataMode, DataFreshness, HealthResponse, SystemStatus
from app.providers.registry import get_registry
from app.services.demo_data import AMPHAN_IBTRACS_SID
from app.services.ingestion import get_last_ingestion_time, get_active_ni_storms

router = APIRouter(prefix="/api", tags=["health"])

_START_TIME = time.time()


def _detect_device() -> str:
    settings = get_settings()
    if settings.ai_device == "cpu":
        return "cpu"
    if settings.ai_device == "cuda":
        return "cuda"
    try:
        import torch  # noqa: PLC0415
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu (torch not installed)"


@router.get("/health", response_model=HealthResponse, summary="System health check")
async def health() -> HealthResponse:
    """
    Returns the current system health including data provider statuses.

    - **status**: ONLINE | DEGRADED | OFFLINE
    - **provider_statuses**: Status of each data provider
    - **last_ingestion_utc**: When data was last fetched and stored
    - **active_ni_storms**: Count of active NI basin storms in DB
    """
    settings = get_settings()
    uptime = round(time.time() - _START_TIME, 1)

    # Provider statuses from registry
    registry = get_registry()
    provider_statuses = registry.get_provider_statuses()

    # Last ingestion time
    last_ingest: datetime | None = None
    active_count = 0
    try:
        last_ingest = await get_last_ingestion_time()
        active_obs = await get_active_ni_storms(max_age_hours=48)
        # Exclude historical fallback from count
        active_count = sum(1 for o in active_obs if o.cyclone_id != AMPHAN_IBTRACS_SID)
    except Exception:
        pass

    # Determine system status
    ibtracs_ok = provider_statuses.get("ibtracs") in ("ok", None)
    sys_status = SystemStatus.ONLINE if ibtracs_ok else SystemStatus.DEGRADED

    # Data mode
    if active_count > 0:
        data_mode = DataMode.LIVE
    elif last_ingest:
        data_mode = DataMode.HISTORICAL
    else:
        data_mode = DataMode.DEMO

    return HealthResponse(
        status=sys_status,
        version=settings.app_version,
        demo_mode=settings.demo_mode,
        data_mode=data_mode,
        device=_detect_device(),
        timestamp_utc=datetime.now(timezone.utc),
        uptime_seconds=uptime,
        sources={
            "ibtracs": "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/",
            "rsmc_bulletin": settings.rsmc_bulletin_url,
            "mosdac": settings.mosdac_api_url,
            "database": settings.database_url.split("://", 1)[0] + "://[configured]",
        },
        provider_statuses=provider_statuses if provider_statuses else {
            "ibtracs": "pending",
            "rsmc_bulletin": "disabled" if not settings.rsmc_bulletin_enabled else "pending",
            "historical": "available",
        },
        last_ingestion_utc=last_ingest,
        active_ni_storms=active_count,
    )
