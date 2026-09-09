"""
CycloneAI — IBTrACS Data Provider (Phase 2 — PRIMARY)

Source:     NOAA NCEI IBTrACS v04r01
URL:        https://www.ncei.noaa.gov/data/international-best-track-archive-
            for-climate-stewardship-ibtracs/v04r01/access/csv/
Auth:       None — fully public
Format:     CSV (header row + units row + data rows)
Update:     ~6-hourly for ACTIVE file
Basin:      NI (North Indian Ocean = Bay of Bengal + Arabian Sea)

Key columns used:
  SID              — IBTrACS storm ID (unique per storm)
  NAME             — Storm name
  BASIN            — Basin code (NI for North Indian)
  ISO_TIME         — Observation time UTC
  LAT, LON         — WMO best position
  WMO_WIND         — WMO maximum sustained wind (kt, 10-min)
  WMO_PRES         — WMO central pressure (mb/hPa)
  WMO_AGENCY       — Reporting agency (imd = India Meteorological Dept)
  NEWDELHI_LAT     — IMD/RSMC New Delhi latitude
  NEWDELHI_LON     — IMD/RSMC New Delhi longitude
  NEWDELHI_WIND    — IMD wind speed (kt, 3-min sustained)
  NEWDELHI_PRES    — IMD central pressure (hPa)
  NEWDELHI_GRADE   — IMD intensity grade
  TRACK_TYPE       — main | provisional | PROVISIONAL
  STORM_SPEED      — Translation speed (kt)
  STORM_DIR        — Translation direction (degrees)

IMD/RSMC values (NEWDELHI_*) are preferred over WMO values for NI basin.
WMO values are used as fallback with explicit source attribution.

Limitations:
  - 6-hour latency: active storm data is ~6h behind real-time
  - PROVISIONAL track may be revised in post-season reanalysis
  - No forecast track data (only observed best-track)
  - NEWDELHI columns may be empty for non-NI storms or early observations
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from app.config import get_settings
from app.providers.base import (
    CycloneDataProvider,
    ProviderResult,
    ProviderStatus,
    RawObservation,
)

logger = logging.getLogger("cyclone_ai.providers.ibtracs")

# IBTrACS CSV has a header row then a units row before data rows
_HEADER_ROW = 0
_UNITS_ROW = 1
_DATA_START_ROW = 2


def _kt_to_kmh(kt: Optional[float]) -> Optional[float]:
    """Convert knots to km/h. 1 kt = 1.852 km/h."""
    if kt is None:
        return None
    return round(kt * 1.852, 1)


def _parse_float(val: str) -> Optional[float]:
    """Parse a CSV cell to float; return None if empty or invalid."""
    v = val.strip()
    if not v or v in ("", " "):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _parse_datetime(val: str) -> Optional[datetime]:
    """Parse IBTrACS ISO_TIME string to timezone-aware UTC datetime."""
    v = val.strip()
    if not v:
        return None
    try:
        # Format: "2020-05-18 12:00:00"
        dt = datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _imd_grade_to_category(grade: str) -> Optional[str]:
    """
    Map NEWDELHI_GRADE (numeric IMD scale) to IMD intensity category name.
    IMD Grade scale for NI basin:
      1 = Depression (D)
      2 = Deep Depression (DD)
      3 = Cyclonic Storm (CS)
      4 = Severe Cyclonic Storm (SCS)
      5 = Very Severe Cyclonic Storm (VSCS)
      6 = Extremely Severe Cyclonic Storm (ESCS)
      7 = Super Cyclonic Storm (SuCS)
    """
    _MAP = {
        "1": "Depression",
        "2": "Deep Depression",
        "3": "Cyclonic Storm",
        "4": "Severe Cyclonic Storm",
        "5": "Very Severe Cyclonic Storm",
        "6": "Extremely Severe Cyclonic Storm",
        "7": "Super Cyclonic Storm",
    }
    return _MAP.get(grade.strip())


def _wind_to_category(wind_kt: Optional[float]) -> Optional[str]:
    """
    Derive IMD intensity category from wind speed (kt, 3-min) when
    NEWDELHI_GRADE is not available.
    IMD scale (3-min sustained, kt):
      < 17        = Depression
      17–27       = Deep Depression
      28–47       = Cyclonic Storm
      48–63       = Severe Cyclonic Storm
      64–89       = Very Severe Cyclonic Storm
      90–119      = Extremely Severe Cyclonic Storm
      ≥ 120       = Super Cyclonic Storm
    """
    if wind_kt is None:
        return None
    if wind_kt < 17:
        return "Depression"
    if wind_kt < 28:
        return "Deep Depression"
    if wind_kt < 48:
        return "Cyclonic Storm"
    if wind_kt < 64:
        return "Severe Cyclonic Storm"
    if wind_kt < 90:
        return "Very Severe Cyclonic Storm"
    if wind_kt < 120:
        return "Extremely Severe Cyclonic Storm"
    return "Super Cyclonic Storm"


class IBTracsProvider(CycloneDataProvider):
    """
    IBTrACS ACTIVE CSV provider.

    Fetches ibtracs.ACTIVE.list.v04r01.csv from NOAA NCEI and returns
    all North Indian Ocean (NI) basin observations, using IMD/RSMC
    NEWDELHI_* columns as the primary data source.
    """

    @property
    def name(self) -> str:
        return "ibtracs"

    @property
    def display_name(self) -> str:
        return "IBTrACS v04r01 / IMD-RSMC New Delhi"

    @property
    def source_url(self) -> Optional[str]:
        settings = get_settings()
        return settings.ibtracs_base_url + settings.ibtracs_active_file

    @property
    def update_frequency(self) -> str:
        return "6h"

    async def is_available(self) -> bool:
        """HEAD request to check reachability."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    self.source_url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return resp.status == 200
        except Exception as exc:
            logger.warning("IBTrACS availability check failed: %s", exc)
            return False

    async def fetch(self) -> ProviderResult:
        """
        Download ACTIVE CSV and return NI basin observations.
        Never raises — errors are captured in ProviderResult.
        """
        url = self.source_url
        received_at = datetime.now(timezone.utc)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=60),
                    headers={"User-Agent": "CycloneAI/0.2 (research; contact via github)"},
                ) as resp:
                    if resp.status != 200:
                        return ProviderResult(
                            provider_name=self.name,
                            status=ProviderStatus.ERROR,
                            error_message=f"HTTP {resp.status} from {url}",
                            source_url=url,
                        )
                    text = await resp.text(encoding="utf-8", errors="replace")

        except aiohttp.ClientError as exc:
            logger.error("IBTrACS fetch network error: %s", exc)
            return ProviderResult(
                provider_name=self.name,
                status=ProviderStatus.UNAVAILABLE,
                error_message=str(exc),
                source_url=url,
            )
        except Exception as exc:
            logger.exception("IBTrACS fetch unexpected error: %s", exc)
            return ProviderResult(
                provider_name=self.name,
                status=ProviderStatus.ERROR,
                error_message=str(exc),
                source_url=url,
            )

        observations = self._parse_csv(text, received_at)
        logger.info(
            "IBTrACS: fetched %d NI basin observations from ACTIVE file",
            len(observations)
        )

        return ProviderResult(
            provider_name=self.name,
            status=ProviderStatus.OK,
            observations=observations,
            fetched_at_utc=received_at,
            source_url=url,
        )

    def _parse_csv(
        self, text: str, received_at: datetime
    ) -> list[RawObservation]:
        """
        Parse IBTrACS CSV text.
        Rows 0 = header, 1 = units, 2+ = data.
        Returns only NI basin rows with valid position data.
        """
        observations: list[RawObservation] = []
        reader = csv.DictReader(io.StringIO(text))

        rows_seen = 0
        for row in reader:
            rows_seen += 1
            # Skip the units row (second row — has values like 'degrees_north')
            # IBTrACS CSV structure: row 0 = header, row 1 = units, row 2+ = data.
            # The units row contains descriptive strings in data columns.
            if rows_seen == 1:
                sid_val = row.get("SID", "").strip()
                lat_val = row.get("LAT", "").strip()
                if sid_val.startswith("Year") or "degrees" in lat_val.lower():
                    continue  # this IS the units row
            basin = row.get("BASIN", "").strip()
            if basin != "NI":
                continue

            # --- Position ---
            # Prefer NEWDELHI position; fall back to WMO LAT/LON
            nd_lat = _parse_float(row.get("NEWDELHI_LAT", ""))
            nd_lon = _parse_float(row.get("NEWDELHI_LON", ""))
            wmo_lat = _parse_float(row.get("LAT", ""))
            wmo_lon = _parse_float(row.get("LON", ""))

            lat = nd_lat if nd_lat is not None else wmo_lat
            lon = nd_lon if nd_lon is not None else wmo_lon

            if lat is None or lon is None:
                continue  # skip rows with no position

            # --- Timestamp ---
            ts = _parse_datetime(row.get("ISO_TIME", ""))
            if ts is None:
                continue

            # --- Wind (prefer NEWDELHI, fall back to WMO) ---
            nd_wind = _parse_float(row.get("NEWDELHI_WIND", ""))
            wmo_wind = _parse_float(row.get("WMO_WIND", ""))
            wind_kt = nd_wind if nd_wind is not None else wmo_wind
            used_imd = nd_wind is not None

            # --- Pressure ---
            nd_pres = _parse_float(row.get("NEWDELHI_PRES", ""))
            wmo_pres = _parse_float(row.get("WMO_PRES", ""))
            pressure_hpa = nd_pres if nd_pres is not None else wmo_pres

            # --- Intensity category ---
            nd_grade = row.get("NEWDELHI_GRADE", "").strip()
            category = _imd_grade_to_category(nd_grade) or _wind_to_category(wind_kt)

            # --- Source attribution ---
            if used_imd:
                source_label = (
                    "IBTrACS v04r01 / IMD-RSMC New Delhi (NEWDELHI columns)"
                )
            else:
                source_label = (
                    "IBTrACS v04r01 / WMO best-track (NEWDELHI data unavailable)"
                )

            # --- Movement ---
            speed_kt = _parse_float(row.get("STORM_SPEED", ""))
            direction_deg = _parse_float(row.get("STORM_DIR", ""))
            direction_str = _deg_to_compass(direction_deg) if direction_deg is not None else None
            speed_kmh = _kt_to_kmh(speed_kt)

            # --- Storm ID & name ---
            sid = row.get("SID", "").strip()
            name = row.get("NAME", "").strip() or "UNNAMED"
            season = row.get("SEASON", "").strip()

            # Construct a stable cyclone_id
            cyclone_id = f"{sid}" if sid else f"NI_{name}_{season}"

            obs = RawObservation(
                cyclone_id=cyclone_id,
                cyclone_name=name,
                basin="NI",
                timestamp_utc=ts,
                latitude=lat,
                longitude=lon,
                wind_speed=wind_kt,
                wind_unit="kt",
                central_pressure=pressure_hpa,
                intensity_category=category,
                movement_direction=direction_str,
                movement_speed=speed_kmh,
                source=source_label,
                source_url=self.source_url,
                received_at_utc=received_at,
                raw_data=str(dict(row))[:2000],  # truncate for storage
            )
            observations.append(obs)

        return observations


def _deg_to_compass(deg: float) -> str:
    """Convert degrees to 16-point compass direction."""
    dirs = [
        "N","NNE","NE","ENE","E","ESE","SE","SSE",
        "S","SSW","SW","WSW","W","WNW","NW","NNW",
    ]
    idx = round(deg / 22.5) % 16
    return dirs[idx]
