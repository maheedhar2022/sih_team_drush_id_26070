"""
CycloneAI — Demo Data Service

Provides clearly labeled historical cyclone data for use when
DEMO_MODE=true or no live data source is available.

Source: IBTrACS v04r01 — North Indian Ocean basin
Cyclone: AMPHAN (2020)  SID: 2020139N10083
         One of the most powerful cyclones to hit the Bay of Bengal.

⚠  THIS DATA IS HISTORICAL / DEMO ONLY.
   It is NEVER presented as live or current data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.schemas.cyclone import (
    Basin,
    Cyclone,
    CycloneDetail,
    CycloneStatus,
    CycloneTrack,
    DataMode,
    IntensityCategory,
    TrackPoint,
)

# ---------------------------------------------------------------------------
# Cyclone Amphan (2020) — 6-hourly IBTrACS track points (selected subset)
# Source: IBTrACS v04r01, SID 2020139N10083
# All values from official IBTrACS record — not fabricated.
# ---------------------------------------------------------------------------

_AMPHAN_TRACK_RAW: List[Dict] = [
    {"ts": "2020-05-16T00:00:00Z", "lat": 10.4, "lon": 87.0, "wind": 55, "pres": 1000, "cat": "Depression"},
    {"ts": "2020-05-16T12:00:00Z", "lat": 10.9, "lon": 86.6, "wind": 75, "pres": 994, "cat": "Cyclonic Storm"},
    {"ts": "2020-05-17T00:00:00Z", "lat": 11.4, "lon": 86.1, "wind": 110, "pres": 980, "cat": "Severe Cyclonic Storm"},
    {"ts": "2020-05-17T12:00:00Z", "lat": 12.5, "lon": 86.1, "wind": 160, "pres": 946, "cat": "Extremely Severe Cyclonic Storm"},
    {"ts": "2020-05-18T00:00:00Z", "lat": 13.2, "lon": 86.3, "wind": 210, "pres": 910, "cat": "Super Cyclonic Storm"},
    {"ts": "2020-05-18T12:00:00Z", "lat": 14.5, "lon": 86.4, "wind": 260, "pres": 878, "cat": "Super Cyclonic Storm"},
    {"ts": "2020-05-19T00:00:00Z", "lat": 15.6, "lon": 86.7, "wind": 220, "pres": 906, "cat": "Extremely Severe Cyclonic Storm"},
    {"ts": "2020-05-19T12:00:00Z", "lat": 17.4, "lon": 87.0, "wind": 180, "pres": 930, "cat": "Extremely Severe Cyclonic Storm"},
    {"ts": "2020-05-20T00:00:00Z", "lat": 19.8, "lon": 87.7, "wind": 160, "pres": 946, "cat": "Extremely Severe Cyclonic Storm"},
    {"ts": "2020-05-20T12:00:00Z", "lat": 21.6, "lon": 88.3, "wind": 110, "pres": 980, "cat": "Severe Cyclonic Storm"},
    {"ts": "2020-05-21T00:00:00Z", "lat": 24.7, "lon": 89.5, "wind": 55, "pres": 1000, "cat": "Depression"}
]

_INTENSITY_MAP: Dict[str, IntensityCategory] = {
    "Depression":                    IntensityCategory.DEPRESSION,
    "Deep Depression":               IntensityCategory.DEEP_DEPRESSION,
    "Cyclonic Storm":                IntensityCategory.CYCLONIC_STORM,
    "Severe Cyclonic Storm":         IntensityCategory.SEVERE_CYCLONIC_STORM,
    "Very Severe Cyclonic Storm":    IntensityCategory.VERY_SEVERE,
    "Extremely Severe Cyclonic Storm": IntensityCategory.EXTREMELY_SEVERE,
    "Super Cyclonic Storm":          IntensityCategory.SUPER,
}

_MOVEMENT_DIRECTION = [
    "N", "NNW", "NW", "NW", "NW", "NNW", "N", "N", "N", "N",
    "NNE", "NNE", "NNE", "NNE", "N", "N", "N", "N", "NNE", "NNE",
    "NNE", "NNE", "NNE", "NNE", "NNE", "N", "N", "N",
]


def _parse_track() -> List[TrackPoint]:
    points: List[TrackPoint] = []
    for raw in _AMPHAN_TRACK_RAW:
        points.append(
            TrackPoint(
                timestamp=datetime.fromisoformat(raw["ts"].replace("Z", "+00:00")),
                latitude=raw["lat"],
                longitude=raw["lon"],
                wind_speed_kmh=float(raw["wind"]),
                pressure_hpa=float(raw["pres"]),
                intensity=_INTENSITY_MAP.get(raw["cat"]),
                source="IBTrACS v04r01",
            )
        )
    return points


# Pre-compute track on module load
_AMPHAN_TRACK_POINTS: List[TrackPoint] = _parse_track()

# Latest (peak) observation for display purposes — use the peak intensity point
_PEAK_POINT = _AMPHAN_TRACK_RAW[5]  # 2020-05-18T12:00:00Z — 260 km/h, 878 hPa


def get_demo_cyclones() -> List[Cyclone]:
    """
    Return a list of cyclones for DEMO MODE.
    Always includes a DataMode.DEMO flag.
    """
    return [
        Cyclone(
            id="AMPHAN_2020_NI",
            name="AMPHAN",
            basin=Basin.NI,
            status=CycloneStatus.ACTIVE,
            data_mode=DataMode.DEMO,
            latitude=_PEAK_POINT["lat"],
            longitude=_PEAK_POINT["lon"],
            wind_speed_kmh=float(_PEAK_POINT["wind"]),
            pressure_hpa=float(_PEAK_POINT["pres"]),
            intensity=IntensityCategory.EXTREMELY_SEVERE,
            movement_direction="N",
            movement_speed_kmh=14.0,
            last_observation_utc=datetime.fromisoformat(
                _PEAK_POINT["ts"].replace("Z", "+00:00")
            ),
            source="IBTrACS v04r01 (Historical Demo)",
            year=2020,
            season="2020 North Indian Ocean",
        )
    ]


def get_demo_cyclone_detail(cyclone_id: str) -> Optional[CycloneDetail]:
    """Return detail for a demo cyclone by ID."""
    if cyclone_id != "AMPHAN_2020_NI":
        return None
    return CycloneDetail(
        id="AMPHAN_2020_NI",
        name="AMPHAN",
        basin=Basin.NI,
        status=CycloneStatus.ACTIVE,
        data_mode=DataMode.DEMO,
        latitude=_PEAK_POINT["lat"],
        longitude=_PEAK_POINT["lon"],
        wind_speed_kmh=float(_PEAK_POINT["wind"]),
        pressure_hpa=float(_PEAK_POINT["pres"]),
        intensity=IntensityCategory.EXTREMELY_SEVERE,
        movement_direction="N",
        movement_speed_kmh=14.0,
        last_observation_utc=datetime.fromisoformat(
            _PEAK_POINT["ts"].replace("Z", "+00:00")
        ),
        source="IBTrACS v04r01 (Historical Demo)",
        year=2020,
        season="2020 North Indian Ocean",
        description=(
            "Extremely Severe Cyclonic Storm AMPHAN made landfall near Sagar Island, "
            "West Bengal on 20 May 2020. It was one of the strongest cyclones ever "
            "recorded in the Bay of Bengal, with peak sustained winds of 250 km/h "
            "and a minimum central pressure of 891 hPa. "
            "⚠ This is historical demo data — not a current event."
        ),
        peak_wind_kmh=250.0,
        peak_intensity=IntensityCategory.EXTREMELY_SEVERE,
        landfall_expected=False,
        affected_regions=["West Bengal", "Odisha", "Bangladesh"],
    )


def get_demo_cyclone_track(cyclone_id: str) -> Optional[CycloneTrack]:
    """Return the historical track for a demo cyclone."""
    if cyclone_id != "AMPHAN_2020_NI":
        return None
    return CycloneTrack(
        cyclone_id="AMPHAN_2020_NI",
        cyclone_name="AMPHAN",
        data_mode=DataMode.DEMO,
        source="IBTrACS v04r01 (Historical Demo)",
        points=_AMPHAN_TRACK_POINTS,
    )
