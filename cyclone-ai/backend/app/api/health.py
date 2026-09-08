"""
CycloneAI — Health API Router

GET /api/health
  Returns system status, demo mode flag, AI device, version, and timestamp.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import get_settings
from app.schemas.cyclone import DataMode, HealthResponse, SystemStatus

router = APIRouter(prefix="/api", tags=["health"])

_START_TIME = time.time()


def _detect_device() -> str:
    """Detect whether CUDA is available without importing torch at startup."""
    settings = get_settings()
    if settings.ai_device == "cpu":
        return "cpu"
    if settings.ai_device == "cuda":
        return "cuda"
    # auto-detect
    try:
        import torch  # noqa: PLC0415
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu (torch not installed)"


@router.get("/health", response_model=HealthResponse, summary="System health check")
async def health() -> HealthResponse:
    """
    Returns the current system health.

    - **status**: ONLINE | DEGRADED | OFFLINE
    - **demo_mode**: true when running on historical demo data
    - **device**: cuda or cpu (for AI inference)
    - **sources**: status of external data connectors (Phase 2+)
    """
    settings = get_settings()
    uptime = round(time.time() - _START_TIME, 1)

    return HealthResponse(
        status=SystemStatus.ONLINE,
        version=settings.app_version,
        demo_mode=settings.demo_mode,
        data_mode=DataMode.DEMO if settings.demo_mode else DataMode.LIVE,
        device=_detect_device(),
        timestamp_utc=datetime.now(timezone.utc),
        uptime_seconds=uptime,
        sources={
            "mosdac": "not_configured" if not settings.mosdac_api_key else "pending",
            "ibtracs": "demo_static",
            "database": "not_configured",
        },
    )
