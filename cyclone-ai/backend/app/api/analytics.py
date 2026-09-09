"""
CycloneAI — Analytics & Advanced API Routes (Phase 5)

New endpoints:
  GET /api/cyclones/search           — Historical cyclone search
  GET /api/cyclones/{id}/analytics   — Storm analytics (ACE, RI, translation speed)
  GET /api/cyclones/{id}/alerts      — IMD colour-coded warnings
  GET /api/cyclones/{id}/timeline    — Event timeline (formation → peak → landfall)
  GET /api/cyclones/{id}/risk-zones  — Wind radii as GeoJSON
  GET /api/statistics/seasonal/{y}   — NI basin seasonal statistics
  GET /api/export/cyclone/{id}       — Export cyclone data as CSV/JSON/GeoJSON
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import CycloneObservation
from app.db.session import AsyncSessionLocal
from app.services.analytics import (
    compute_ace,
    compute_alert,
    compute_rapid_intensification,
    compute_risk_zones_geojson,
    compute_seasonal_stats,
    compute_timeline,
    compute_translation_speed,
    search_cyclones,
)

logger = logging.getLogger("cyclone_ai.api.analytics")

router = APIRouter(prefix="/api", tags=["analytics"])


# ---- Helpers ---------------------------------------------------------------

async def _get_observations(cyclone_id: str) -> list[CycloneObservation]:
    """Fetch all observations for a cyclone, ordered by timestamp."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CycloneObservation)
            .where(CycloneObservation.cyclone_id == cyclone_id)
            .order_by(CycloneObservation.timestamp_utc)
        )
        observations = result.scalars().all()
    if not observations:
        raise HTTPException(status_code=404, detail=f"No observations found for cyclone '{cyclone_id}'")
    return list(observations)


async def _get_latest_observation(cyclone_id: str) -> CycloneObservation:
    """Fetch the most recent observation for a cyclone."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CycloneObservation)
            .where(CycloneObservation.cyclone_id == cyclone_id)
            .order_by(CycloneObservation.timestamp_utc.desc())
            .limit(1)
        )
        obs = result.scalar_one_or_none()
    if obs is None:
        raise HTTPException(status_code=404, detail=f"Cyclone '{cyclone_id}' not found")
    return obs


# ---- Search ----------------------------------------------------------------

@router.get(
    "/cyclones/search",
    summary="Search historical cyclones by name, year, basin, or intensity",
)
async def search_cyclones_endpoint(
    name: Optional[str] = Query(None, description="Cyclone name (partial match)"),
    year_min: Optional[int] = Query(None, ge=1980, description="Start year"),
    year_max: Optional[int] = Query(None, le=2030, description="End year"),
    basin: str = Query("NI", description="Basin code (NI, NA, WP, etc.)"),
    intensity: Optional[str] = Query(None, description="Peak intensity category"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
) -> dict:
    settings = get_settings()
    limit = min(limit, settings.search_max_results)
    results = await search_cyclones(
        name=name, year_min=year_min, year_max=year_max,
        basin=basin, intensity=intensity, limit=limit,
    )
    return {
        "count": len(results),
        "results": results,
        "filters": {
            "name": name, "year_min": year_min, "year_max": year_max,
            "basin": basin, "intensity": intensity,
        },
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# ---- Analytics -------------------------------------------------------------

@router.get(
    "/cyclones/{cyclone_id}/analytics",
    summary="Storm analytics — ACE, rapid intensification, translation speed",
)
async def cyclone_analytics(cyclone_id: str) -> dict:
    observations = await _get_observations(cyclone_id)
    latest = observations[-1]

    ace = compute_ace(observations)
    ri_events = compute_rapid_intensification(observations)
    translation = compute_translation_speed(observations)

    # Peak intensity
    peak = max(observations, key=lambda o: o.wind_speed_kmh or 0)
    duration_hours = (
        (observations[-1].timestamp_utc - observations[0].timestamp_utc).total_seconds() / 3600
    )

    return {
        "cyclone_id": cyclone_id,
        "cyclone_name": latest.cyclone_name,
        "analytics": {
            "ace": ace,
            "ace_unit": "10⁴ kt²",
            "peak_wind_kmh": peak.wind_speed_kmh,
            "peak_pressure_hpa": peak.pressure_hpa,
            "peak_intensity": peak.intensity_category,
            "peak_timestamp_utc": peak.timestamp_utc.isoformat(),
            "duration_hours": round(duration_hours, 1),
            "observation_count": len(observations),
            "rapid_intensification_events": ri_events,
            "translation_speed": translation,
        },
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# ---- Alerts ----------------------------------------------------------------

@router.get(
    "/cyclones/{cyclone_id}/alerts",
    summary="IMD colour-coded alert level based on current wind speed",
)
async def cyclone_alerts(cyclone_id: str) -> dict:
    latest = await _get_latest_observation(cyclone_id)
    alert = compute_alert(latest.wind_speed_kmh)

    return {
        "cyclone_id": cyclone_id,
        "cyclone_name": latest.cyclone_name,
        "current_wind_kmh": latest.wind_speed_kmh,
        "current_pressure_hpa": latest.pressure_hpa,
        "intensity_category": latest.intensity_category,
        "alert": alert,
        "observation_utc": latest.timestamp_utc.isoformat(),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# ---- Timeline --------------------------------------------------------------

@router.get(
    "/cyclones/{cyclone_id}/timeline",
    summary="Key milestones — formation, intensification, peak, landfall, dissipation",
)
async def cyclone_timeline(cyclone_id: str) -> dict:
    observations = await _get_observations(cyclone_id)
    timeline = compute_timeline(observations)

    return {
        "cyclone_id": cyclone_id,
        "cyclone_name": observations[-1].cyclone_name,
        "event_count": len(timeline),
        "events": timeline,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# ---- Risk Zones ------------------------------------------------------------

@router.get(
    "/cyclones/{cyclone_id}/risk-zones",
    summary="Concentric wind-risk zones as GeoJSON for map overlay",
)
async def cyclone_risk_zones(cyclone_id: str) -> dict:
    latest = await _get_latest_observation(cyclone_id)
    geojson = compute_risk_zones_geojson(
        lat=latest.latitude,
        lon=latest.longitude,
        wind_kmh=latest.wind_speed_kmh,
        cyclone_name=latest.cyclone_name,
    )
    return geojson


# ---- Seasonal Statistics ---------------------------------------------------

@router.get(
    "/statistics/seasonal/{year}",
    summary="NI basin seasonal statistics — total storms, ACE, strongest storm",
)
async def seasonal_statistics(year: int) -> dict:
    settings = get_settings()
    current_year = datetime.now(timezone.utc).year
    if year < settings.stats_min_year or year > current_year:
        raise HTTPException(
            status_code=400,
            detail=f"Year must be between {settings.stats_min_year} and {current_year}",
        )
    stats = await compute_seasonal_stats(year)
    return {
        **stats,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# ---- Export ----------------------------------------------------------------

@router.get(
    "/export/cyclone/{cyclone_id}",
    summary="Export cyclone track data as CSV, JSON, or GeoJSON",
)
async def export_cyclone(
    cyclone_id: str,
    format: str = Query("csv", description="Export format: csv, json, geojson"),
) -> StreamingResponse | dict:
    settings = get_settings()
    allowed_formats = [f.strip() for f in settings.export_formats.split(",")]
    if format not in allowed_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{format}'. Allowed: {allowed_formats}",
        )

    observations = await _get_observations(cyclone_id)

    if format == "json":
        return {
            "cyclone_id": cyclone_id,
            "cyclone_name": observations[-1].cyclone_name,
            "observation_count": len(observations),
            "observations": [
                {
                    "timestamp_utc": obs.timestamp_utc.isoformat(),
                    "latitude": obs.latitude,
                    "longitude": obs.longitude,
                    "wind_speed_kmh": obs.wind_speed_kmh,
                    "pressure_hpa": obs.pressure_hpa,
                    "intensity_category": obs.intensity_category,
                    "source": obs.source,
                }
                for obs in observations
            ],
        }

    if format == "geojson":
        coordinates = [[obs.longitude, obs.latitude] for obs in observations]
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "cyclone_id": cyclone_id,
                        "cyclone_name": observations[-1].cyclone_name,
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coordinates,
                    },
                },
                # Individual observation points
                *[
                    {
                        "type": "Feature",
                        "properties": {
                            "timestamp_utc": obs.timestamp_utc.isoformat(),
                            "wind_speed_kmh": obs.wind_speed_kmh,
                            "pressure_hpa": obs.pressure_hpa,
                            "intensity": obs.intensity_category,
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [obs.longitude, obs.latitude],
                        },
                    }
                    for obs in observations
                ],
            ],
        }

    # CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp_utc", "latitude", "longitude",
        "wind_speed_kmh", "pressure_hpa", "intensity_category", "source",
    ])
    for obs in observations:
        writer.writerow([
            obs.timestamp_utc.isoformat(), obs.latitude, obs.longitude,
            obs.wind_speed_kmh, obs.pressure_hpa, obs.intensity_category, obs.source,
        ])
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={cyclone_id}_track.csv"},
    )
