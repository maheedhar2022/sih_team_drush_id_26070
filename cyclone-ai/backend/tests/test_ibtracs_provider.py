"""
Tests for IBTrACS Provider (Phase 2)

Tests:
  - CSV parsing with valid NI basin data
  - NI basin filter (non-NI rows excluded)
  - NEWDELHI column extraction (IMD values preferred)
  - WMO fallback when NEWDELHI columns are empty
  - Unit conversion: knots → km/h
  - Coordinate validation
  - Malformed row handling
  - Missing fields (graceful null handling)
  - Source attribution on every observation
  - Empty CSV handling
  - Invalid timestamp handling
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.ibtracs import IBTracsProvider, _kt_to_kmh, _parse_float, _parse_datetime, _imd_grade_to_category, _wind_to_category
from app.providers.base import ProviderStatus

# ---------------------------------------------------------------------------
# Minimal valid IBTrACS CSV — NI basin row
# ---------------------------------------------------------------------------
_HEADER = (
    "SID,SEASON,NUMBER,BASIN,SUBBASIN,NAME,ISO_TIME,NATURE,LAT,LON,"
    "WMO_WIND,WMO_PRES,WMO_AGENCY,TRACK_TYPE,DIST2LAND,LANDFALL,IFLAG,"
    "USA_AGENCY,USA_ATCF_ID,USA_LAT,USA_LON,USA_RECORD,USA_STATUS,USA_WIND,USA_PRES,"
    "USA_SSHS,USA_R34_NE,USA_R34_SE,USA_R34_SW,USA_R34_NW,USA_R50_NE,USA_R50_SE,"
    "USA_R50_SW,USA_R50_NW,USA_R64_NE,USA_R64_SE,USA_R64_SW,USA_R64_NW,USA_POCI,"
    "USA_ROCI,USA_RMW,USA_EYE,TOKYO_LAT,TOKYO_LON,TOKYO_GRADE,TOKYO_WIND,TOKYO_PRES,"
    "TOKYO_R50_DIR,TOKYO_R50_LONG,TOKYO_R50_SHORT,TOKYO_R30_DIR,TOKYO_R30_LONG,"
    "TOKYO_R30_SHORT,TOKYO_LAND,CMA_LAT,CMA_LON,CMA_CAT,CMA_WIND,CMA_PRES,"
    "HKO_LAT,HKO_LON,HKO_CAT,HKO_WIND,HKO_PRES,KMA_LAT,KMA_LON,KMA_CAT,KMA_WIND,"
    "KMA_PRES,KMA_R50_DIR,KMA_R50_LONG,KMA_R50_SHORT,KMA_R30_DIR,KMA_R30_LONG,"
    "KMA_R30_SHORT,NEWDELHI_LAT,NEWDELHI_LON,NEWDELHI_GRADE,NEWDELHI_WIND,"
    "NEWDELHI_PRES,NEWDELHI_CI,NEWDELHI_DP,NEWDELHI_POCI,REUNION_LAT,REUNION_LON,"
    "REUNION_TYPE,REUNION_WIND,REUNION_PRES,REUNION_TNUM,REUNION_CI,REUNION_RMW,"
    "REUNION_R34_NE,REUNION_R34_SE,REUNION_R34_SW,REUNION_R34_NW,REUNION_R50_NE,"
    "REUNION_R50_SE,REUNION_R50_SW,REUNION_R50_NW,REUNION_R64_NE,REUNION_R64_SE,"
    "REUNION_R64_SW,REUNION_R64_NW,BOM_LAT,BOM_LON,BOM_TYPE,BOM_WIND,BOM_PRES,"
    "BOM_TNUM,BOM_CI,BOM_RMW,BOM_R34_NE,BOM_R34_SE,BOM_R34_SW,BOM_R34_NW,"
    "BOM_R50_NE,BOM_R50_SE,BOM_R50_SW,BOM_R50_NW,BOM_R64_NE,BOM_R64_SE,BOM_R64_NW,"
    "BOM_R64_SW,BOM_ROCI,BOM_POCI,BOM_EYE,BOM_POS_METHOD,BOM_PRES_METHOD,"
    "NADI_LAT,NADI_LON,NADI_CAT,NADI_WIND,NADI_PRES,WELLINGTON_LAT,WELLINGTON_LON,"
    "WELLINGTON_WIND,WELLINGTON_PRES,DS824_LAT,DS824_LON,DS824_STAGE,DS824_WIND,"
    "DS824_PRES,TD9636_LAT,TD9636_LON,TD9636_STAGE,TD9636_WIND,TD9636_PRES,"
    "TD9635_LAT,TD9635_LON,TD9635_WIND,TD9635_PRES,TD9635_ROCI,NEUMANN_LAT,"
    "NEUMANN_LON,NEUMANN_CLASS,NEUMANN_WIND,NEUMANN_PRES,MLC_LAT,MLC_LON,"
    "MLC_CLASS,MLC_WIND,MLC_PRES,USA_GUST,BOM_GUST,BOM_GUST_PER,REUNION_GUST,"
    "REUNION_GUST_PER,USA_SEAHGT,USA_SEARAD_NE,USA_SEARAD_SE,USA_SEARAD_SW,"
    "USA_SEARAD_NW,STORM_SPEED,STORM_DIR"
)
_UNITS = " ,Year, , , , , , ,degrees_north,degrees_east,kts,mb, , ,km,km, , , ,degrees_north,degrees_east, , ,kts,mb,1,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,mb,nmile,nmile,nmile,degrees_north,degrees_east,1,kts,mb, ,nmile,nmile, ,nmile,nmile,1,degrees_north,degrees_east,1,kts,mb,degrees_north,degrees_east, ,kts,mb,degrees_north,degrees_east, ,kts,mb, ,nmile,nmile, ,nmile,nmile,degrees_north,degrees_east, ,kts,mb,1,mb,mb,degrees_north,degrees_east, ,kts,mb,1,1,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,degrees_north,degrees_east, ,kts,mb,1,1,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,nmile,mb,nmile, , ,degrees_north,degrees_east,1,kts,mb,degrees_north,degrees_east,kts,mb,degrees_north,degrees_east, ,kts,mb,degrees_north,degrees_east, ,kts,mb,degrees_north,degrees_east,kts,mb,nmile,degrees_north,degrees_east, ,kts,mb,degrees_north,degrees_east, ,kts,mb,kts,kts,second,kts,second,ft,nmile,nmile,nmile,nmile,kts,degrees"


def _make_row(
    sid="2020136N10088", basin="NI", name="AMPHAN",
    iso_time="2020-05-18 18:00:00",
    lat="14.5", lon="86.3",
    wmo_wind="130", wmo_pres="920",
    nd_lat="14.5", nd_lon="86.3",
    nd_grade="7", nd_wind="130", nd_pres="920",
    storm_speed="14", storm_dir="315",
) -> str:
    """Build a minimal CSV data row with enough columns to match the header."""
    n_cols = len(_HEADER.split(","))
    # Build a blank row then fill in the columns we care about
    fields = [""] * n_cols
    col_names = _HEADER.split(",")

    def set_col(name, val):
        try:
            idx = col_names.index(name)
            fields[idx] = val
        except ValueError:
            pass

    set_col("SID", sid)
    set_col("BASIN", basin)
    set_col("NAME", name)
    set_col("ISO_TIME", iso_time)
    set_col("LAT", lat)
    set_col("LON", lon)
    set_col("WMO_WIND", wmo_wind)
    set_col("WMO_PRES", wmo_pres)
    set_col("NEWDELHI_LAT", nd_lat)
    set_col("NEWDELHI_LON", nd_lon)
    set_col("NEWDELHI_GRADE", nd_grade)
    set_col("NEWDELHI_WIND", nd_wind)
    set_col("NEWDELHI_PRES", nd_pres)
    set_col("STORM_SPEED", storm_speed)
    set_col("STORM_DIR", storm_dir)
    set_col("SEASON", "2020")
    return ",".join(fields)


def _make_csv(*data_rows) -> str:
    return "\n".join([_HEADER, _UNITS, *data_rows])


# ---------------------------------------------------------------------------
# Unit helper tests
# ---------------------------------------------------------------------------

def test_kt_to_kmh_basic():
    assert _kt_to_kmh(1.0) == pytest.approx(1.9, rel=1e-1)   # rounds to 1 decimal: 1.852 → 1.9
    assert _kt_to_kmh(130.0) == pytest.approx(240.76, rel=1e-3)
    assert _kt_to_kmh(None) is None


def test_parse_float_valid():
    assert _parse_float("14.5") == 14.5
    assert _parse_float(" 86.3 ") == 86.3
    assert _parse_float("") is None
    assert _parse_float(" ") is None
    assert _parse_float("abc") is None


def test_parse_datetime_valid():
    dt = _parse_datetime("2020-05-18 18:00:00")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2020
    assert dt.month == 5
    assert dt.day == 18
    assert dt.hour == 18


def test_parse_datetime_invalid():
    assert _parse_datetime("") is None
    assert _parse_datetime("not-a-date") is None


def test_imd_grade_to_category():
    assert _imd_grade_to_category("7") == "Super Cyclonic Storm"
    assert _imd_grade_to_category("6") == "Extremely Severe Cyclonic Storm"
    assert _imd_grade_to_category("5") == "Very Severe Cyclonic Storm"
    assert _imd_grade_to_category("4") == "Severe Cyclonic Storm"
    assert _imd_grade_to_category("3") == "Cyclonic Storm"
    assert _imd_grade_to_category("2") == "Deep Depression"
    assert _imd_grade_to_category("1") == "Depression"
    assert _imd_grade_to_category("") is None
    assert _imd_grade_to_category("99") is None


def test_wind_to_category_boundaries():
    assert _wind_to_category(None) is None
    assert _wind_to_category(10.0) == "Depression"
    assert _wind_to_category(17.0) == "Deep Depression"
    assert _wind_to_category(28.0) == "Cyclonic Storm"
    assert _wind_to_category(64.0) == "Very Severe Cyclonic Storm"
    assert _wind_to_category(90.0) == "Extremely Severe Cyclonic Storm"
    assert _wind_to_category(120.0) == "Super Cyclonic Storm"


# ---------------------------------------------------------------------------
# CSV parsing tests
# ---------------------------------------------------------------------------

def test_parse_valid_ni_row():
    provider = IBTracsProvider()
    csv_text = _make_csv(_make_row())
    received_at = datetime.now(timezone.utc)
    obs = provider._parse_csv(csv_text, received_at)

    assert len(obs) == 1
    o = obs[0]
    assert o.cyclone_name == "AMPHAN"
    assert o.basin == "NI"
    assert o.latitude == pytest.approx(14.5, rel=1e-3)
    assert o.longitude == pytest.approx(86.3, rel=1e-3)
    assert o.wind_speed == pytest.approx(130.0, rel=1e-3)
    assert o.wind_unit == "kt"
    assert o.central_pressure == pytest.approx(920.0, rel=1e-3)
    assert o.intensity_category == "Super Cyclonic Storm"
    assert "IMD" in o.source or "NEWDELHI" in o.source
    assert o.source_url is not None


def test_ni_filter_excludes_other_basins():
    provider = IBTracsProvider()
    na_row = _make_row(basin="NA", name="DOLLY")
    ni_row = _make_row(basin="NI", name="AMPHAN")
    csv_text = _make_csv(na_row, ni_row)
    obs = provider._parse_csv(csv_text, datetime.now(timezone.utc))
    assert len(obs) == 1
    assert obs[0].cyclone_name == "AMPHAN"


def test_newdelhi_preferred_over_wmo():
    """NEWDELHI columns take priority over WMO columns."""
    provider = IBTracsProvider()
    # Different WMO vs NEWDELHI values
    row = _make_row(
        wmo_wind="140", wmo_pres="910",
        nd_wind="130", nd_pres="920",
        nd_lat="14.5", nd_lon="86.3",
    )
    csv_text = _make_csv(row)
    obs = provider._parse_csv(csv_text, datetime.now(timezone.utc))
    assert len(obs) == 1
    # Should use NEWDELHI values
    assert obs[0].wind_speed == pytest.approx(130.0, rel=1e-3)
    assert obs[0].central_pressure == pytest.approx(920.0, rel=1e-3)
    assert "NEWDELHI" in obs[0].source or "IMD" in obs[0].source


def test_wmo_fallback_when_newdelhi_empty():
    """Falls back to WMO values when NEWDELHI columns are empty."""
    provider = IBTracsProvider()
    row = _make_row(
        wmo_wind="100", wmo_pres="970",
        nd_lat="", nd_lon="", nd_grade="", nd_wind="", nd_pres="",
        lat="10.0", lon="85.0",
    )
    csv_text = _make_csv(row)
    obs = provider._parse_csv(csv_text, datetime.now(timezone.utc))
    assert len(obs) == 1
    assert obs[0].wind_speed == pytest.approx(100.0, rel=1e-3)
    assert obs[0].central_pressure == pytest.approx(970.0, rel=1e-3)
    assert "WMO" in obs[0].source


def test_malformed_row_skipped():
    """Rows with no valid position are skipped (not crashed)."""
    provider = IBTracsProvider()
    bad_row = _make_row(lat="", lon="", nd_lat="", nd_lon="")
    good_row = _make_row()
    csv_text = _make_csv(bad_row, good_row)
    obs = provider._parse_csv(csv_text, datetime.now(timezone.utc))
    assert len(obs) == 1  # only good row parsed


def test_missing_wind_stored_as_none():
    """Missing wind/pressure stored as None, not fabricated."""
    provider = IBTracsProvider()
    row = _make_row(wmo_wind="", wmo_pres="", nd_wind="", nd_pres="")
    csv_text = _make_csv(row)
    obs = provider._parse_csv(csv_text, datetime.now(timezone.utc))
    assert len(obs) == 1
    assert obs[0].wind_speed is None
    assert obs[0].central_pressure is None


def test_source_attribution_always_present():
    """Every observation must have non-empty source."""
    provider = IBTracsProvider()
    csv_text = _make_csv(_make_row())
    obs = provider._parse_csv(csv_text, datetime.now(timezone.utc))
    for o in obs:
        assert o.source
        assert len(o.source) > 0


def test_empty_csv_returns_no_observations():
    provider = IBTracsProvider()
    obs = provider._parse_csv(_HEADER + "\n" + _UNITS + "\n", datetime.now(timezone.utc))
    assert obs == []


def test_timestamp_is_utc_aware():
    provider = IBTracsProvider()
    csv_text = _make_csv(_make_row())
    obs = provider._parse_csv(csv_text, datetime.now(timezone.utc))
    assert obs[0].timestamp_utc.tzinfo is not None


def test_coordinate_extraction():
    provider = IBTracsProvider()
    row = _make_row(nd_lat="21.65", nd_lon="88.3")
    obs = provider._parse_csv(_make_csv(row), datetime.now(timezone.utc))
    assert obs[0].latitude == pytest.approx(21.65, rel=1e-3)
    assert obs[0].longitude == pytest.approx(88.3, rel=1e-3)


@pytest.mark.asyncio
async def test_fetch_network_failure_returns_error():
    """Network failure returns ProviderStatus.UNAVAILABLE — never raises."""
    provider = IBTracsProvider()
    with patch("aiohttp.ClientSession") as mock_session:
        mock_session.return_value.__aenter__.side_effect = Exception("Network down")
        result = await provider.fetch()
    assert result.status in (ProviderStatus.UNAVAILABLE, ProviderStatus.ERROR)
    assert result.observations == []
    assert result.error_message is not None


@pytest.mark.asyncio
async def test_fetch_http_error_returns_error():
    """HTTP 500 returns ProviderStatus.ERROR — never raises."""
    provider = IBTracsProvider()

    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.get.return_value = mock_response

    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = await provider.fetch()

    assert result.status == ProviderStatus.ERROR
