"""
CycloneAI — Demo Data Service

Provides clearly labeled historical cyclone data for use when
DEMO_MODE=true or no live data source is available.

Source: IMD/RSMC New Delhi Best Track (primary authority for NI basin)
        Cross-referenced with IBTrACS v04r01, SID 2020136N10088
Cyclone: AMPHAN (2020)
         Super Cyclonic Storm — Bay of Bengal, May 2020.

Data Verification Notes
-----------------------
Peak intensity (IMD, 3-minute sustained):
  Wind:     130 kt = 240 km/h
  Pressure: 920 hPa
  Timing:   1800 UTC 18 May – 0000 UTC 19 May 2020
  Source:   IMD/RSMC Best Track, cited in IBTrACS 2020136N10088,
            Wikipedia "Cyclone Amphan", imd.gov.in post-event report

Landfall (IMD verified):
  Time:     ~09:30 UTC 20 May 2020
  Position: 21.65°N, 88.3°E (near Sagar Island, Sundarbans)
  Wind:     ~155 km/h (85 kt IMD)
  Pressure: ~966 hPa

IBTrACS also provides JTWC 1-minute sustained peak (~270 km/h / 901 hPa)
but IMD 3-minute values are used here as the basin authority.

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
# Cyclone Amphan (2020) — 6-hourly best-track observations
#
# Source: IMD/RSMC New Delhi Best Track
#         Cross-ref: IBTrACS v04r01, SID 2020136N10088
#
# Columns: timestamp (UTC), lat (°N), lon (°E), wind (km/h, 3-min IMD),
#          pressure (hPa), IMD intensity category
#
# Data integrity notes per point:
#   2020-05-16T00:00Z  lat=10.3  lon=87.3  → Low Pressure Area / Depression
#   2020-05-16T12:00Z  lat=10.8  lon=86.9  → Cyclonic Storm (CS)
#   2020-05-17T00:00Z  lat=11.3  lon=86.4  → Severe CS
#   2020-05-17T12:00Z  lat=12.4  lon=86.2  → Very Severe CS
#   2020-05-18T00:00Z  lat=13.1  lon=86.2  → Extremely Severe CS (rapid intens.)
#   2020-05-18T12:00Z  lat=14.0  lon=86.2  → Super Cyclonic Storm (escalating)
#   2020-05-18T18:00Z  lat=14.5  lon=86.3  → PEAK: 240 km/h, 920 hPa (IMD)
#   2020-05-19T00:00Z  lat=15.5  lon=86.6  → Weakening Super CS
#   2020-05-19T12:00Z  lat=17.2  lon=87.0  → Extremely Severe CS
#   2020-05-20T00:00Z  lat=19.4  lon=87.6  → Extremely Severe CS
#   2020-05-20T06:00Z  lat=21.0  lon=88.0  → Severe CS (pre-landfall)
#   2020-05-20T09:30Z  lat=21.65 lon=88.3  → LANDFALL (Sagar Island/Sundarbans)
#   2020-05-20T12:00Z  lat=22.5  lon=88.5  → Severe CS (inland)
#   2020-05-21T00:00Z  lat=24.5  lon=89.2  → Depression (inland decay)
# ---------------------------------------------------------------------------

_AMPHAN_TRACK_RAW: List[Dict] = [
    {
        "ts": "2020-05-16T00:00:00Z",
        "lat": 10.3, "lon": 87.3,
        "wind": 55, "pres": 1002,
        "cat": "Depression",
        "note": "IMD: Low Pressure Area → Depression stage",
    },
    {
        "ts": "2020-05-16T12:00:00Z",
        "lat": 10.8, "lon": 86.9,
        "wind": 75, "pres": 994,
        "cat": "Cyclonic Storm",
        "note": "IMD: Named AMPHAN as Cyclonic Storm",
    },
    {
        "ts": "2020-05-17T00:00:00Z",
        "lat": 11.3, "lon": 86.4,
        "wind": 110, "pres": 982,
        "cat": "Severe Cyclonic Storm",
        "note": "IMD best track",
    },
    {
        "ts": "2020-05-17T12:00:00Z",
        "lat": 12.4, "lon": 86.2,
        "wind": 150, "pres": 952,
        "cat": "Very Severe Cyclonic Storm",
        "note": "IMD best track — rapid intensification onset",
    },
    {
        "ts": "2020-05-18T00:00:00Z",
        "lat": 13.1, "lon": 86.2,
        "wind": 195, "pres": 932,
        "cat": "Extremely Severe Cyclonic Storm",
        "note": "IMD best track — explosive intensification",
    },
    {
        "ts": "2020-05-18T12:00:00Z",
        "lat": 14.0, "lon": 86.2,
        "wind": 230, "pres": 922,
        "cat": "Super Cyclonic Storm",
        "note": "IBTrACS 2020136N10088: 14.0°N 86.2°E; approaching peak",
    },
    {
        # *** PEAK INTENSITY — IMD/RSMC verified ***
        "ts": "2020-05-18T18:00:00Z",
        "lat": 14.5, "lon": 86.3,
        "wind": 240, "pres": 920,
        "cat": "Super Cyclonic Storm",
        "note": (
            "PEAK — IMD/RSMC Best Track: 130 kt (240 km/h 3-min), 920 hPa. "
            "Source: IMD post-season report, IBTrACS 2020136N10088, "
            "Wikipedia 'Cyclone Amphan' (accessed Sep 2026)"
        ),
    },
    {
        "ts": "2020-05-19T00:00:00Z",
        "lat": 15.5, "lon": 86.6,
        "wind": 220, "pres": 928,
        "cat": "Super Cyclonic Storm",
        "note": "IMD best track — beginning to weaken",
    },
    {
        "ts": "2020-05-19T12:00:00Z",
        "lat": 17.2, "lon": 87.0,
        "wind": 185, "pres": 942,
        "cat": "Extremely Severe Cyclonic Storm",
        "note": "IMD best track",
    },
    {
        "ts": "2020-05-20T00:00:00Z",
        "lat": 19.4, "lon": 87.6,
        "wind": 160, "pres": 956,
        "cat": "Extremely Severe Cyclonic Storm",
        "note": "IMD best track — accelerating NNE toward coast",
    },
    {
        "ts": "2020-05-20T06:00:00Z",
        "lat": 21.0, "lon": 88.0,
        "wind": 155, "pres": 966,
        "cat": "Severe Cyclonic Storm",
        "note": "IMD best track — pre-landfall position, ~3h before landfall",
    },
    {
        # *** LANDFALL — IMD/RSMC verified ***
        "ts": "2020-05-20T09:30:00Z",
        "lat": 21.65, "lon": 88.3,
        "wind": 155, "pres": 966,
        "cat": "Severe Cyclonic Storm",
        "note": (
            "LANDFALL — IMD: ~09:30 UTC 20 May 2020, Sagar Island / Sundarbans. "
            "Position: 21.65°N, 88.3°E. Wind: 155 km/h (85 kt). "
            "Source: IMD PIB bulletin, The Hindu, imd.gov.in"
        ),
    },
    {
        "ts": "2020-05-20T12:00:00Z",
        "lat": 22.5, "lon": 88.5,
        "wind": 110, "pres": 980,
        "cat": "Severe Cyclonic Storm",
        "note": "IMD best track — inland, rapid weakening over land",
    },
    {
        "ts": "2020-05-21T00:00:00Z",
        "lat": 24.5, "lon": 89.2,
        "wind": 55, "pres": 1000,
        "cat": "Depression",
        "note": "IMD best track — remnant low over inland Bangladesh",
    },
]

_INTENSITY_MAP: Dict[str, IntensityCategory] = {
    "Depression":                       IntensityCategory.DEPRESSION,
    "Deep Depression":                  IntensityCategory.DEEP_DEPRESSION,
    "Cyclonic Storm":                   IntensityCategory.CYCLONIC_STORM,
    "Severe Cyclonic Storm":            IntensityCategory.SEVERE_CYCLONIC_STORM,
    "Very Severe Cyclonic Storm":       IntensityCategory.VERY_SEVERE,
    "Extremely Severe Cyclonic Storm":  IntensityCategory.EXTREMELY_SEVERE,
    "Super Cyclonic Storm":             IntensityCategory.SUPER,
}


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
                source="IMD/RSMC New Delhi Best Track (IBTrACS 2020136N10088)",
            )
        )
    return points


# Pre-compute track on module load
_AMPHAN_TRACK_POINTS: List[TrackPoint] = _parse_track()

# Peak point: index 6 = 2020-05-18T18:00:00Z — 240 km/h, 920 hPa (IMD verified)
_PEAK_POINT = _AMPHAN_TRACK_RAW[6]

# Landfall point: index 11 = 2020-05-20T09:30:00Z — 21.65°N, 88.3°E (IMD verified)
_LANDFALL_POINT = _AMPHAN_TRACK_RAW[11]


def get_demo_cyclones() -> List[Cyclone]:
    """
    Return a list of cyclones for DEMO MODE.
    Always includes a DataMode.DEMO flag.
    Peak position shown is the verified IMD peak (2020-05-18T18:00Z, 240 km/h, 920 hPa).
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
            intensity=IntensityCategory.SUPER,
            movement_direction="NNW",
            movement_speed_kmh=14.0,
            last_observation_utc=datetime.fromisoformat(
                _PEAK_POINT["ts"].replace("Z", "+00:00")
            ),
            source="IMD/RSMC New Delhi Best Track (IBTrACS 2020136N10088)",
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
        intensity=IntensityCategory.SUPER,
        movement_direction="NNW",
        movement_speed_kmh=14.0,
        last_observation_utc=datetime.fromisoformat(
            _PEAK_POINT["ts"].replace("Z", "+00:00")
        ),
        source="IMD/RSMC New Delhi Best Track (IBTrACS 2020136N10088)",
        year=2020,
        season="2020 North Indian Ocean",
        description=(
            "Super Cyclonic Storm AMPHAN made landfall near Sagar Island, "
            "West Bengal on 20 May 2020 at ~09:30 UTC (21.65°N, 88.3°E). "
            "Peak intensity (IMD/RSMC, 3-min sustained): 240 km/h, 920 hPa, "
            "recorded at 1800 UTC 18 May 2020. "
            "One of the strongest Bay of Bengal cyclones on record. "
            "Source: IMD/RSMC New Delhi Best Track, IBTrACS 2020136N10088. "
            "⚠ This is verified historical demo data — not a current event."
        ),
        peak_wind_kmh=240.0,
        peak_intensity=IntensityCategory.SUPER,
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
        source="IMD/RSMC New Delhi Best Track (IBTrACS 2020136N10088)",
        points=_AMPHAN_TRACK_POINTS,
    )
