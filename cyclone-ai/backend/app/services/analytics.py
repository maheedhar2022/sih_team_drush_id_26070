"""
CycloneAI — Cyclone Analytics Service (Phase 5)

Provides computed analytics, alerts, timeline milestones, and risk-zone
GeoJSON from existing observation data. No external API calls needed —
everything is derived from the database.
"""
from __future__ import annotations

import math
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, distinct

from app.config import get_settings
from app.db.models import CycloneObservation
from app.db.session import AsyncSessionLocal

logger = logging.getLogger("cyclone_ai.services.analytics")


# ---------------------------------------------------------------------------
# Analytics (ACE, intensification rate, etc.)
# ---------------------------------------------------------------------------

def _kmh_to_kt(kmh: Optional[float]) -> Optional[float]:
    """Convert km/h to knots."""
    if kmh is None:
        return None
    return kmh / 1.852


def compute_ace(observations: list[CycloneObservation]) -> float:
    """
    Accumulated Cyclone Energy (ACE).
    ACE = Σ (Vmax²) for each 6-hourly observation where Vmax ≥ 34 kt.
    Units: 10⁴ kt².
    """
    ace = 0.0
    for obs in observations:
        v_kt = _kmh_to_kt(obs.wind_speed_kmh)
        if v_kt is not None and v_kt >= 34.0:
            ace += v_kt ** 2
    return round(ace / 1e4, 4)


def compute_rapid_intensification(observations: list[CycloneObservation]) -> list[dict]:
    """
    Detect rapid intensification (RI) events.
    RI = wind speed increase ≥ 30 kt (55.6 km/h) in 24 hours.
    """
    events = []
    for i, obs in enumerate(observations):
        if obs.wind_speed_kmh is None:
            continue
        # Look back ~24h (4 × 6-hourly observations)
        for j in range(max(0, i - 4), i):
            prev = observations[j]
            if prev.wind_speed_kmh is None:
                continue
            hours_diff = (obs.timestamp_utc - prev.timestamp_utc).total_seconds() / 3600
            if 20 <= hours_diff <= 28:  # ~24h window
                increase = obs.wind_speed_kmh - prev.wind_speed_kmh
                if increase >= 55.6:  # 30 kt in km/h
                    events.append({
                        "start_utc": prev.timestamp_utc.isoformat(),
                        "end_utc": obs.timestamp_utc.isoformat(),
                        "hours": round(hours_diff, 1),
                        "wind_increase_kmh": round(increase, 1),
                        "wind_start_kmh": prev.wind_speed_kmh,
                        "wind_end_kmh": obs.wind_speed_kmh,
                    })
    return events


def compute_translation_speed(observations: list[CycloneObservation]) -> list[dict]:
    """Compute translation speed between consecutive observations."""
    speeds = []
    for i in range(1, len(observations)):
        prev, curr = observations[i - 1], observations[i]
        dt_hours = (curr.timestamp_utc - prev.timestamp_utc).total_seconds() / 3600
        if dt_hours <= 0:
            continue
        dist_km = _haversine(prev.latitude, prev.longitude, curr.latitude, curr.longitude)
        speed_kmh = round(dist_km / dt_hours, 1)
        speeds.append({
            "timestamp_utc": curr.timestamp_utc.isoformat(),
            "speed_kmh": speed_kmh,
            "distance_km": round(dist_km, 1),
        })
    return speeds


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Alerts (IMD colour-coded)
# ---------------------------------------------------------------------------

def compute_alert(wind_kmh: Optional[float]) -> dict:
    """
    Compute IMD colour-coded alert from current wind speed.
    Green  : No significant weather
    Yellow : Cyclonic Storm (62–87 km/h)
    Orange : Severe Cyclonic Storm (88–117 km/h)
    Red    : Very Severe or higher (≥118 km/h)
    """
    settings = get_settings()
    if wind_kmh is None or wind_kmh < settings.alert_yellow_wind_kmh:
        return {
            "colour": "GREEN",
            "level": "No Warning",
            "description": "No significant cyclonic activity. No action required.",
            "action": "Monitor weather updates.",
        }
    if wind_kmh < settings.alert_orange_wind_kmh:
        return {
            "colour": "YELLOW",
            "level": "Watch",
            "description": "Cyclonic Storm — moderate winds expected. Be prepared.",
            "action": "Secure loose objects. Fishermen should not venture into the sea.",
        }
    if wind_kmh < settings.alert_red_wind_kmh:
        return {
            "colour": "ORANGE",
            "level": "Alert",
            "description": "Severe Cyclonic Storm — dangerous conditions likely.",
            "action": "Evacuate low-lying areas. Stock essentials. Follow local authorities.",
        }
    return {
        "colour": "RED",
        "level": "Warning",
        "description": "Very Severe / Extremely Severe / Super Cyclonic Storm — extreme danger.",
        "action": "Immediate evacuation from coastal and flood-prone areas. Take shelter.",
    }


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def compute_timeline(observations: list[CycloneObservation]) -> list[dict]:
    """
    Extract key milestones from the observation track:
    - Formation, naming, intensity escalations, peak, landfall, dissipation.
    """
    if not observations:
        return []

    events = []
    prev_cat = None

    # Formation
    events.append({
        "type": "FORMATION",
        "timestamp_utc": observations[0].timestamp_utc.isoformat(),
        "latitude": observations[0].latitude,
        "longitude": observations[0].longitude,
        "description": f"System first detected as {observations[0].intensity_category or 'Low Pressure Area'}",
    })

    peak_wind = 0.0
    peak_obs = observations[0]

    for obs in observations:
        # Track intensity transitions
        if obs.intensity_category and obs.intensity_category != prev_cat:
            if prev_cat is not None:
                events.append({
                    "type": "INTENSITY_CHANGE",
                    "timestamp_utc": obs.timestamp_utc.isoformat(),
                    "latitude": obs.latitude,
                    "longitude": obs.longitude,
                    "description": f"Intensified to {obs.intensity_category}" if (obs.wind_speed_kmh or 0) > peak_wind else f"Weakened to {obs.intensity_category}",
                })
            prev_cat = obs.intensity_category

        # Track peak
        if obs.wind_speed_kmh and obs.wind_speed_kmh > peak_wind:
            peak_wind = obs.wind_speed_kmh
            peak_obs = obs

    # Peak intensity
    if peak_wind > 0:
        events.append({
            "type": "PEAK_INTENSITY",
            "timestamp_utc": peak_obs.timestamp_utc.isoformat(),
            "latitude": peak_obs.latitude,
            "longitude": peak_obs.longitude,
            "description": f"Peak intensity: {peak_obs.wind_speed_kmh} km/h, {peak_obs.pressure_hpa} hPa — {peak_obs.intensity_category}",
        })

    # Detect landfall (track crosses from sea to near coast — simplified: lat > 20°N over Indian coast)
    for i in range(1, len(observations)):
        prev, curr = observations[i - 1], observations[i]
        # Simple heuristic: significant wind at lat > 20 and previous latitude was < 20
        if curr.latitude >= 20.0 and prev.latitude < 20.0 and (curr.wind_speed_kmh or 0) >= 60:
            events.append({
                "type": "LANDFALL",
                "timestamp_utc": curr.timestamp_utc.isoformat(),
                "latitude": curr.latitude,
                "longitude": curr.longitude,
                "description": f"Landfall at {curr.latitude:.2f}°N, {curr.longitude:.2f}°E with winds of {curr.wind_speed_kmh} km/h",
            })
            break

    # Dissipation
    last = observations[-1]
    events.append({
        "type": "DISSIPATION",
        "timestamp_utc": last.timestamp_utc.isoformat(),
        "latitude": last.latitude,
        "longitude": last.longitude,
        "description": f"System weakened to {last.intensity_category or 'remnant low'}",
    })

    # Sort chronologically
    events.sort(key=lambda e: e["timestamp_utc"])
    return events


# ---------------------------------------------------------------------------
# Risk Zones (GeoJSON)
# ---------------------------------------------------------------------------

def compute_risk_zones_geojson(
    lat: float, lon: float, wind_kmh: Optional[float], cyclone_name: str
) -> dict:
    """
    Generate GeoJSON FeatureCollection with concentric risk-zone circles.
    Uses configurable radii from settings.
    """
    settings = get_settings()
    radii = sorted(settings.risk_zone_radii_km, reverse=True)  # outermost first
    labels = ["Outer Risk Zone", "Middle Risk Zone", "Inner Risk Zone"]
    colours = ["#FFEB3B", "#FF9800", "#F44336"]  # yellow, orange, red

    features = []
    for i, radius_km in enumerate(radii):
        label = labels[i] if i < len(labels) else f"Zone {i + 1}"
        colour = colours[i] if i < len(colours) else "#999"
        circle_coords = _circle_polygon(lat, lon, radius_km)
        features.append({
            "type": "Feature",
            "properties": {
                "zone": label,
                "radius_km": radius_km,
                "colour": colour,
                "cyclone_name": cyclone_name,
                "wind_speed_kmh": wind_kmh,
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [circle_coords],
            },
        })

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "center_lat": lat,
            "center_lon": lon,
            "cyclone_name": cyclone_name,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    }


def _circle_polygon(lat: float, lon: float, radius_km: float, n_points: int = 64) -> list[list[float]]:
    """Generate polygon coordinates approximating a circle on the globe."""
    coords = []
    for i in range(n_points + 1):
        angle = math.radians(360 * i / n_points)
        dlat = radius_km / 111.32 * math.cos(angle)
        dlon = radius_km / (111.32 * math.cos(math.radians(lat))) * math.sin(angle)
        coords.append([round(lon + dlon, 6), round(lat + dlat, 6)])
    return coords


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def search_cyclones(
    *,
    name: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    basin: str = "NI",
    intensity: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Search historical cyclone observations with filters."""
    async with AsyncSessionLocal() as session:
        # Get distinct cyclone IDs matching filters
        query = (
            select(
                CycloneObservation.cyclone_id,
                CycloneObservation.cyclone_name,
                CycloneObservation.basin,
                func.max(CycloneObservation.wind_speed_kmh).label("peak_wind_kmh"),
                func.min(CycloneObservation.pressure_hpa).label("min_pressure_hpa"),
                func.min(CycloneObservation.timestamp_utc).label("start_date"),
                func.max(CycloneObservation.timestamp_utc).label("end_date"),
                func.count().label("observation_count"),
            )
            .where(CycloneObservation.basin == basin)
            .group_by(CycloneObservation.cyclone_id, CycloneObservation.cyclone_name, CycloneObservation.basin)
        )

        if name:
            query = query.having(
                func.upper(CycloneObservation.cyclone_name).contains(name.upper())
            )
        if year_min:
            query = query.having(
                func.extract("year", func.min(CycloneObservation.timestamp_utc)) >= year_min
            )
        if year_max:
            query = query.having(
                func.extract("year", func.max(CycloneObservation.timestamp_utc)) <= year_max
            )
        if intensity:
            query = query.having(
                func.max(CycloneObservation.intensity_category) == intensity
            )

        query = query.order_by(func.max(CycloneObservation.timestamp_utc).desc()).limit(limit)
        result = await session.execute(query)
        rows = result.all()

    return [
        {
            "cyclone_id": row.cyclone_id,
            "cyclone_name": row.cyclone_name,
            "basin": row.basin,
            "peak_wind_kmh": row.peak_wind_kmh,
            "min_pressure_hpa": row.min_pressure_hpa,
            "start_date": row.start_date.isoformat() if row.start_date else None,
            "end_date": row.end_date.isoformat() if row.end_date else None,
            "observation_count": row.observation_count,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Seasonal Statistics
# ---------------------------------------------------------------------------

async def compute_seasonal_stats(year: int) -> dict:
    """Compute seasonal statistics for a given year in the NI basin."""
    async with AsyncSessionLocal() as session:
        # Count distinct storms
        storm_count_result = await session.execute(
            select(func.count(distinct(CycloneObservation.cyclone_id)))
            .where(
                CycloneObservation.basin == "NI",
                func.extract("year", CycloneObservation.timestamp_utc) == year,
            )
        )
        storm_count = storm_count_result.scalar() or 0

        # Get all observations for ACE calculation
        obs_result = await session.execute(
            select(CycloneObservation)
            .where(
                CycloneObservation.basin == "NI",
                func.extract("year", CycloneObservation.timestamp_utc) == year,
            )
            .order_by(CycloneObservation.timestamp_utc)
        )
        all_obs = obs_result.scalars().all()

        # Find strongest storm
        strongest = None
        if all_obs:
            peak = max(all_obs, key=lambda o: o.wind_speed_kmh or 0)
            if peak.wind_speed_kmh:
                strongest = {
                    "cyclone_id": peak.cyclone_id,
                    "cyclone_name": peak.cyclone_name,
                    "peak_wind_kmh": peak.wind_speed_kmh,
                    "pressure_hpa": peak.pressure_hpa,
                    "intensity": peak.intensity_category,
                }

    return {
        "year": year,
        "basin": "NI",
        "total_storms": storm_count,
        "ace": compute_ace(list(all_obs)),
        "strongest_storm": strongest,
        "observation_count": len(all_obs),
    }
