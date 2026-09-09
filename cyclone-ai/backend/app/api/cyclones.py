"""
CycloneAI — Cyclones API Router (Phase 2)

Endpoints:
  GET /api/cyclones/active           — Active NI storms (IBTrACS or historical fallback)
  GET /api/cyclones/{id}             — Single cyclone detail
  GET /api/cyclones/{id}/track       — Full observed track
  GET /api/cyclones/{id}/forecast    — Official forecast track (if available)
  GET /api/sources                   — Data source registry

Data flow:
  1. Query DB for recent NI observations (ingestion populates DB on startup)
  2. If active storms found → return them with correct DataFreshness
  3. If no active storms → return verified historical AMPHAN (HISTORICAL mode)
  4. If DB unavailable → return DATA_SOURCE_UNAVAILABLE (503) — never fabricate

No silent fallback to demo data when live/historical data should be present.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.db.models import CycloneObservation
from app.schemas.cyclone import (
    ActiveCyclonesResponse,
    Basin,
    Cyclone,
    CycloneDetail,
    CycloneStatus,
    CycloneTrack,
    DataFreshness,
    DataMode,
    DataSourceInfo,
    DataSourcesResponse,
    ForecastPoint,
    ForecastTrack,
    IntensityCategory,
    TrackPoint,
)
from app.services.ingestion import (
    get_active_ni_storms,
    get_cyclone_track,
    get_data_sources,
    get_last_ingestion_time,
    get_latest_cyclone_forecast,
)
from app.services.demo_data import (
    get_demo_cyclone_detail,
    get_demo_cyclone_track,
    get_demo_cyclones,
)

logger = logging.getLogger("cyclone_ai.api.cyclones")
router = APIRouter(prefix="/api/cyclones", tags=["cyclones"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _intensity_from_str(s: Optional[str]) -> Optional[IntensityCategory]:
    if not s:
        return None
    for cat in IntensityCategory:
        if cat.value.lower() == s.lower():
            return cat
    return None


def _freshness_from_str(s: Optional[str]) -> DataFreshness:
    if not s:
        return DataFreshness.DEMO
    try:
        return DataFreshness(s)
    except ValueError:
        return DataFreshness.HISTORICAL


def _obs_to_cyclone(obs: CycloneObservation) -> Cyclone:
    """Convert a DB CycloneObservation to API Cyclone model."""
    freshness = _freshness_from_str(obs.data_freshness)
    if freshness in (DataFreshness.LIVE, DataFreshness.DELAYED):
        data_mode = DataMode.LIVE if freshness == DataFreshness.LIVE else DataMode.DELAYED
    elif freshness == DataFreshness.STALE:
        data_mode = DataMode.DELAYED
    else:
        data_mode = DataMode.HISTORICAL

    return Cyclone(
        id=obs.cyclone_id,
        name=obs.cyclone_name,
        basin=Basin.NI,
        status=CycloneStatus.ACTIVE,
        data_mode=data_mode,
        data_freshness=freshness,
        latitude=obs.latitude,
        longitude=obs.longitude,
        wind_speed_kmh=obs.wind_speed_kmh,
        pressure_hpa=obs.pressure_hpa,
        intensity=_intensity_from_str(obs.intensity_category),
        movement_direction=obs.movement_direction,
        movement_speed_kmh=obs.movement_speed_kmh,
        last_observation_utc=obs.timestamp_utc,
        received_at_utc=obs.received_at_utc,
        source=obs.source,
        source_url=obs.source_url,
        year=obs.timestamp_utc.year,
        season=f"{obs.timestamp_utc.year} North Indian Ocean",
    )


def _obs_to_track_point(obs: CycloneObservation) -> TrackPoint:
    return TrackPoint(
        timestamp=obs.timestamp_utc,
        latitude=obs.latitude,
        longitude=obs.longitude,
        wind_speed_kmh=obs.wind_speed_kmh,
        pressure_hpa=obs.pressure_hpa,
        intensity=_intensity_from_str(obs.intensity_category),
        source=obs.source,
        data_freshness=_freshness_from_str(obs.data_freshness),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=ActiveCyclonesResponse,
    summary="List current and historical-fallback cyclone systems",
)
async def list_cyclones() -> ActiveCyclonesResponse:
    """Backward-compatible collection endpoint for the documented API contract."""
    return await list_active_cyclones()


@router.get(
    "/active",
    response_model=ActiveCyclonesResponse,
    summary="List active NI basin cyclone systems",
)
async def list_active_cyclones() -> ActiveCyclonesResponse:
    """
    Returns currently active North Indian Ocean cyclone systems.

    Data priority:
    1. IBTrACS ACTIVE (live/recent) — observations from last 48h in DB
    2. Historical AMPHAN 2020 — if no active storms (DataMode.HISTORICAL)

    DataFreshness in response:
    - LIVE     — data < 6h old
    - DELAYED  — data 6–24h old
    - STALE    — data > 24h old
    - HISTORICAL — verified historical dataset (no active storms)
    """
    now = datetime.now(timezone.utc)

    try:
        active_obs = await get_active_ni_storms(max_age_hours=48)
    except Exception as exc:
        logger.exception("DB query for active storms failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=(
                "Cyclone observations are temporarily unavailable. "
                "Historical mode is not used as a substitute for an unavailable database."
            ),
        ) from exc

    if active_obs:
        # Live/recent storms found
        cyclones = [_obs_to_cyclone(obs) for obs in active_obs]

        # Exclude historical fallback if it shows up in active query
        cyclones = [c for c in cyclones if c.id != "2020136N10088"]

        if cyclones:
            freshness_values = [c.data_freshness for c in cyclones]
            best_freshness = (
                DataFreshness.LIVE if DataFreshness.LIVE in freshness_values
                else DataFreshness.DELAYED if DataFreshness.DELAYED in freshness_values
                else DataFreshness.STALE
            )
            return ActiveCyclonesResponse(
                data_mode=DataMode.LIVE if best_freshness == DataFreshness.LIVE else DataMode.DELAYED,
                data_freshness=best_freshness,
                count=len(cyclones),
                cyclones=cyclones,
                retrieved_at_utc=now,
                source="IBTrACS v04r01 / IMD-RSMC New Delhi",
                note=(
                    f"Data from IBTrACS ACTIVE file. "
                    f"Freshness: {best_freshness.value}. "
                    f"IBTrACS has ~6h latency for active storms."
                ),
            )

    # No active storms — return verified historical data with explicit labelling
    logger.info("No active NI storms in DB — returning historical AMPHAN dataset")
    demo_cyclones = get_demo_cyclones()
    # Convert demo cyclones to Cyclone with HISTORICAL freshness
    cyclones = []
    for c in demo_cyclones:
        cyclones.append(Cyclone(
            id=c.id,
            name=c.name,
            basin=c.basin,
            status=c.status,
            data_mode=DataMode.HISTORICAL,
            data_freshness=DataFreshness.HISTORICAL,
            latitude=c.latitude,
            longitude=c.longitude,
            wind_speed_kmh=c.wind_speed_kmh,
            pressure_hpa=c.pressure_hpa,
            intensity=c.intensity,
            movement_direction=c.movement_direction,
            movement_speed_kmh=c.movement_speed_kmh,
            last_observation_utc=c.last_observation_utc,
            source=c.source,
            source_url="https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/",
            year=c.year,
            season=c.season,
        ))

    return ActiveCyclonesResponse(
        data_mode=DataMode.HISTORICAL,
        data_freshness=DataFreshness.HISTORICAL,
        count=len(cyclones),
        cyclones=cyclones,
        retrieved_at_utc=now,
        source="IMD/RSMC New Delhi Best Track (IBTrACS 2020136N10088)",
        note=(
            "⚠ HISTORICAL MODE: No active NI basin storms detected. "
            "Displaying verified historical data: AMPHAN 2020 "
            "(IMD/RSMC New Delhi Best Track, IBTrACS 2020136N10088). "
            "This is NOT a current event."
        ),
    )


@router.get(
    "/{cyclone_id}",
    response_model=CycloneDetail,
    summary="Get detailed information for a specific cyclone",
)
async def get_cyclone_detail(cyclone_id: str) -> CycloneDetail:
    # Try DB first
    try:
        track_obs = await get_cyclone_track(cyclone_id)
        if track_obs:
            latest = track_obs[-1]
            peak_wind = max(
                (o.wind_speed_kmh for o in track_obs if o.wind_speed_kmh),
                default=None
            )
            freshness = _freshness_from_str(latest.data_freshness)
            data_mode = (
                DataMode.LIVE if freshness == DataFreshness.LIVE
                else DataMode.HISTORICAL
            )
            return CycloneDetail(
                id=cyclone_id,
                name=latest.cyclone_name,
                basin=Basin.NI,
                status=CycloneStatus.ACTIVE,
                data_mode=data_mode,
                data_freshness=freshness,
                latitude=latest.latitude,
                longitude=latest.longitude,
                wind_speed_kmh=latest.wind_speed_kmh,
                pressure_hpa=latest.pressure_hpa,
                intensity=_intensity_from_str(latest.intensity_category),
                movement_direction=latest.movement_direction,
                movement_speed_kmh=latest.movement_speed_kmh,
                last_observation_utc=latest.timestamp_utc,
                received_at_utc=latest.received_at_utc,
                source=latest.source,
                source_url=latest.source_url,
                year=latest.timestamp_utc.year,
                season=f"{latest.timestamp_utc.year} North Indian Ocean",
                description=None,
                peak_wind_kmh=peak_wind,
                peak_intensity=None,
                landfall_expected=None,
                affected_regions=[],
            )
    except Exception as exc:
        logger.warning("DB lookup failed for %s: %s", cyclone_id, exc)

    # Fall back to historical demo data
    detail = get_demo_cyclone_detail(cyclone_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Cyclone '{cyclone_id}' not found.",
        )
    return detail


@router.get(
    "/{cyclone_id}/track",
    response_model=CycloneTrack,
    summary="Get the observed track for a specific cyclone",
)
async def get_cyclone_track_endpoint(cyclone_id: str) -> CycloneTrack:
    try:
        track_obs = await get_cyclone_track(cyclone_id)
        if track_obs:
            points = [_obs_to_track_point(o) for o in track_obs]
            source = track_obs[0].source if track_obs else "Unknown"
            freshness = _freshness_from_str(track_obs[-1].data_freshness) if track_obs else DataFreshness.DEMO
            return CycloneTrack(
                cyclone_id=cyclone_id,
                cyclone_name=track_obs[0].cyclone_name if track_obs else cyclone_id,
                data_mode=DataMode.LIVE if freshness == DataFreshness.LIVE else DataMode.HISTORICAL,
                source=source,
                points=points,
            )
    except Exception as exc:
        logger.warning("DB track lookup failed for %s: %s", cyclone_id, exc)

    # Fall back to historical
    track = get_demo_cyclone_track(cyclone_id)
    if track is None:
        raise HTTPException(
            status_code=404,
            detail=f"Track for cyclone '{cyclone_id}' not found.",
        )
    return track


@router.get(
    "/{cyclone_id}/forecast",
    response_model=ForecastTrack,
    summary="Get official forecast track (RSMC New Delhi)",
)
async def get_cyclone_forecast(cyclone_id: str) -> ForecastTrack:
    """
    Returns official forecast track from RSMC New Delhi (if available).
    Currently requires RSMC_BULLETIN_ENABLED=true and an active storm.
    Returns 404 when no forecast is available (no fabrication).
    """
    forecast_rows = await get_latest_cyclone_forecast(cyclone_id)
    if forecast_rows:
        latest = forecast_rows[0]
        return ForecastTrack(
            cyclone_id=cyclone_id,
            cyclone_name=latest.cyclone_name or cyclone_id,
            issued_at_utc=latest.issued_at_utc,
            source=latest.source,
            source_url=latest.source_url,
            points=[
                ForecastPoint(
                    issued_at_utc=row.issued_at_utc,
                    valid_at_utc=row.valid_at_utc,
                    forecast_hour=row.forecast_hour,
                    latitude=row.latitude,
                    longitude=row.longitude,
                    wind_speed_kmh=row.wind_speed_kmh,
                    pressure_hpa=row.pressure_hpa,
                    intensity=_intensity_from_str(row.intensity_category),
                    source=row.source,
                    source_url=row.source_url,
                )
                for row in forecast_rows
            ],
        )

    raise HTTPException(
        status_code=404,
        detail=(
            f"No official forecast track available for '{cyclone_id}'. "
            "RSMC New Delhi forecast integration requires RSMC_BULLETIN_ENABLED=true "
            "and an active storm bulletin. See /api/sources for provider status."
        ),
    )


@router.get(
    "/sources/list",
    response_model=DataSourcesResponse,
    summary="List all data sources and their status",
)
async def list_data_sources() -> DataSourcesResponse:
    """
    Returns the registry of all data sources with their operational status.
    Use this for source transparency display in the frontend.
    """
    try:
        db_sources = await get_data_sources()
        sources = [
            DataSourceInfo(
                name=s.name,
                display_name=s.display_name,
                url=s.url,
                auth_type=s.auth_type,
                update_frequency=s.update_frequency,
                last_fetched_utc=s.last_fetched_utc,
                last_status=s.last_status,
                last_error=s.last_error,
                enabled=s.enabled,
            )
            for s in db_sources
        ]
    except Exception as exc:
        logger.warning("Could not fetch data sources from DB: %s", exc)
        sources = []

    return DataSourcesResponse(
        sources=sources,
        retrieved_at_utc=datetime.now(timezone.utc),
    )
