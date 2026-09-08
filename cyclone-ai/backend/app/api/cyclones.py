"""
CycloneAI — Cyclones API Router

GET /api/cyclones/active             — List active / demo cyclones
GET /api/cyclones/{cyclone_id}       — Single cyclone detail
GET /api/cyclones/{cyclone_id}/track — Full track points
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas.cyclone import (
    ActiveCyclonesResponse,
    CycloneDetail,
    CycloneTrack,
    DataMode,
)
from app.services.demo_data import (
    get_demo_cyclone_detail,
    get_demo_cyclone_track,
    get_demo_cyclones,
)

router = APIRouter(prefix="/api/cyclones", tags=["cyclones"])


@router.get(
    "/active",
    response_model=ActiveCyclonesResponse,
    summary="List all active tropical cyclone systems",
)
async def list_active_cyclones() -> ActiveCyclonesResponse:
    """
    Returns currently active cyclone systems.

    In **DEMO MODE** this returns historical data from IBTrACS clearly
    labeled with `data_mode: DEMO`.  Live data will be available in Phase 2.
    """
    settings = get_settings()

    if settings.demo_mode:
        cyclones = get_demo_cyclones()
        return ActiveCyclonesResponse(
            data_mode=DataMode.DEMO,
            count=len(cyclones),
            cyclones=cyclones,
            retrieved_at_utc=datetime.now(timezone.utc),
            source="IBTrACS v04r01 (Historical Demo)",
            note=(
                "⚠ DEMO MODE: Displaying historical Cyclone AMPHAN (2020) data. "
                "This is NOT a current event. Real-time data integration is Phase 2."
            ),
        )

    # Phase 2+: Live source integration
    return ActiveCyclonesResponse(
        data_mode=DataMode.OFFLINE,
        count=0,
        cyclones=[],
        retrieved_at_utc=datetime.now(timezone.utc),
        source="N/A",
        note="Live data sources not yet configured. Enable DEMO_MODE=true for demo data.",
    )


@router.get(
    "/{cyclone_id}",
    response_model=CycloneDetail,
    summary="Get detailed information for a specific cyclone",
)
async def get_cyclone_detail(cyclone_id: str) -> CycloneDetail:
    settings = get_settings()

    if settings.demo_mode:
        detail = get_demo_cyclone_detail(cyclone_id)
        if detail is None:
            raise HTTPException(
                status_code=404,
                detail=f"Cyclone '{cyclone_id}' not found in demo dataset.",
            )
        return detail

    raise HTTPException(
        status_code=503,
        detail="Live data sources not yet configured.",
    )


@router.get(
    "/{cyclone_id}/track",
    response_model=CycloneTrack,
    summary="Get the observed track for a specific cyclone",
)
async def get_cyclone_track(cyclone_id: str) -> CycloneTrack:
    settings = get_settings()

    if settings.demo_mode:
        track = get_demo_cyclone_track(cyclone_id)
        if track is None:
            raise HTTPException(
                status_code=404,
                detail=f"Track for cyclone '{cyclone_id}' not found in demo dataset.",
            )
        return track

    raise HTTPException(
        status_code=503,
        detail="Live data sources not yet configured.",
    )
