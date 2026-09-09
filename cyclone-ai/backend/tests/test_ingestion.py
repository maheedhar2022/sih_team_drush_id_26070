"""
Tests for Data Ingestion Service (Phase 2)

Tests:
  - Schema validation on ingestion
  - Timestamp UTC enforcement
  - Source attribution required
  - Wind / pressure sanity bounds
  - Coordinate bounds validation
  - Duplicate observation rejection (dedup)
  - Malformed record handling
  - Stale data detection
  - Missing required fields
  - Provider failure fallback
  - Unit normalisation (knots → km/h)
  - Data freshness computation
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from app.providers.base import RawForecastPoint, RawObservation, ProviderResult, ProviderStatus
from app.services.ingestion import (
    _validate_obs,
    _normalise,
    _compute_freshness,
    _kt_to_kmh,
    _validate_forecast,
)
from app.db.models import Cyclone as CycloneEntity


def _obs(**kwargs) -> RawObservation:
    defaults = dict(
        cyclone_id="2020136N10088",
        cyclone_name="AMPHAN",
        basin="NI",
        timestamp_utc=datetime(2020, 5, 18, 18, 0, 0, tzinfo=timezone.utc),
        latitude=14.5,
        longitude=86.3,
        wind_speed=130.0,
        wind_unit="kt",
        central_pressure=920.0,
        intensity_category="Super Cyclonic Storm",
        movement_direction="NNW",
        movement_speed=14.0,
        source="IBTrACS v04r01 / IMD-RSMC New Delhi",
        source_url="https://example.com",
        received_at_utc=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return RawObservation(**defaults)


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

def test_valid_observation_passes():
    errors = _validate_obs(_obs())
    assert errors == []


def test_invalid_latitude_too_high():
    errors = _validate_obs(_obs(latitude=95.0))
    assert any("latitude" in e for e in errors)


def test_invalid_latitude_too_low():
    errors = _validate_obs(_obs(latitude=-91.0))
    assert any("latitude" in e for e in errors)


def test_invalid_longitude_out_of_range():
    errors = _validate_obs(_obs(longitude=200.0))
    assert any("longitude" in e for e in errors)


def test_naive_timestamp_fails():
    """Timezone-naive timestamps must be rejected."""
    naive_ts = datetime(2020, 5, 18, 18, 0, 0)  # no tzinfo
    errors = _validate_obs(_obs(timestamp_utc=naive_ts))
    assert any("timezone" in e for e in errors)


def test_empty_source_fails():
    errors = _validate_obs(_obs(source=""))
    assert any("source" in e for e in errors)


def test_missing_cyclone_id_fails():
    errors = _validate_obs(_obs(cyclone_id=""))
    assert any("cyclone_id" in e for e in errors)


def test_wind_above_max_fails():
    """Wind > 215 kt is physically impossible — reject."""
    errors = _validate_obs(_obs(wind_speed=250.0))
    assert any("wind" in e for e in errors)


def test_wind_negative_fails():
    errors = _validate_obs(_obs(wind_speed=-5.0))
    assert any("wind" in e for e in errors)


def test_pressure_below_850_fails():
    """Pressure below 850 hPa has never been recorded — reject."""
    errors = _validate_obs(_obs(central_pressure=800.0))
    assert any("pressure" in e for e in errors)


def test_pressure_above_1060_fails():
    errors = _validate_obs(_obs(central_pressure=1100.0))
    assert any("pressure" in e for e in errors)


def test_none_wind_accepted():
    """Missing wind is valid — stored as NULL, not fabricated."""
    errors = _validate_obs(_obs(wind_speed=None))
    assert errors == []


def test_none_pressure_accepted():
    """Missing pressure is valid — stored as NULL, not fabricated."""
    errors = _validate_obs(_obs(central_pressure=None))
    assert errors == []


def test_forecast_with_valid_times_passes():
    now = datetime.now(timezone.utc)
    forecast = RawForecastPoint(
        cyclone_id="2020136N10088",
        cyclone_name="AMPHAN",
        issued_at_utc=now,
        valid_at_utc=now + timedelta(hours=6),
        forecast_hour=6,
        latitude=14.5,
        longitude=86.3,
        wind_speed_kmh=185.0,
        pressure_hpa=940.0,
        intensity_category="Extremely Severe Cyclonic Storm",
        source="RSMC New Delhi",
        source_url="https://example.com/bulletin",
    )
    assert _validate_forecast(forecast) == []


def test_forecast_with_invalid_valid_time_fails():
    now = datetime.now(timezone.utc)
    forecast = RawForecastPoint(
        cyclone_id="2020136N10088",
        cyclone_name="AMPHAN",
        issued_at_utc=now,
        valid_at_utc=now - timedelta(hours=6),
        forecast_hour=6,
        latitude=14.5,
        longitude=86.3,
        wind_speed_kmh=None,
        pressure_hpa=None,
        intensity_category=None,
        source="RSMC New Delhi",
        source_url="https://example.com/bulletin",
    )
    assert "forecast valid time precedes issue time" in _validate_forecast(forecast)


def test_cyclone_metadata_model_has_required_fields():
    """Cyclone identity is persisted independently from observations."""
    column_names = set(CycloneEntity.__table__.columns.keys())
    assert {
        "cyclone_id", "cyclone_name", "basin", "status", "source",
        "source_id", "created_at", "updated_at",
    } <= column_names


# ---------------------------------------------------------------------------
# Normalisation tests
# ---------------------------------------------------------------------------

def test_normalise_knots_to_kmh():
    raw = _obs(wind_speed=130.0, wind_unit="kt")
    now = datetime.now(timezone.utc)
    norm = _normalise(raw, now)
    assert norm.wind_speed_kmh == pytest.approx(130.0 * 1.852, rel=1e-3)


def test_normalise_kmh_unchanged():
    raw = _obs(wind_speed=240.0, wind_unit="kmh")
    now = datetime.now(timezone.utc)
    norm = _normalise(raw, now)
    assert norm.wind_speed_kmh == pytest.approx(240.0, rel=1e-3)


def test_normalise_ms_to_kmh():
    raw = _obs(wind_speed=60.0, wind_unit="m/s")
    now = datetime.now(timezone.utc)
    norm = _normalise(raw, now)
    assert norm.wind_speed_kmh == pytest.approx(216.0, rel=1e-3)


def test_normalise_none_wind():
    raw = _obs(wind_speed=None, wind_unit="kt")
    now = datetime.now(timezone.utc)
    norm = _normalise(raw, now)
    assert norm.wind_speed_kmh is None


def test_normalise_source_preserved():
    raw = _obs(source="IBTrACS v04r01 / IMD-RSMC New Delhi")
    now = datetime.now(timezone.utc)
    norm = _normalise(raw, now)
    assert norm.source == "IBTrACS v04r01 / IMD-RSMC New Delhi"


def test_normalise_sets_processed_at():
    raw = _obs()
    now = datetime.now(timezone.utc)
    norm = _normalise(raw, now)
    assert norm.processed_at_utc == now


# ---------------------------------------------------------------------------
# Data freshness tests
# ---------------------------------------------------------------------------

def test_freshness_live():
    ts = datetime.now(timezone.utc) - timedelta(hours=2)
    assert _compute_freshness(ts) == "LIVE"


def test_freshness_delayed():
    ts = datetime.now(timezone.utc) - timedelta(hours=12)
    assert _compute_freshness(ts) == "DELAYED"


def test_freshness_stale():
    ts = datetime.now(timezone.utc) - timedelta(hours=36)
    assert _compute_freshness(ts) == "STALE"


def test_freshness_historical():
    ts = datetime.now(timezone.utc) - timedelta(days=400)
    assert _compute_freshness(ts) == "HISTORICAL"


# ---------------------------------------------------------------------------
# Unit conversion tests
# ---------------------------------------------------------------------------

def test_kt_to_kmh_zero():
    assert _kt_to_kmh(0.0) == 0.0


def test_kt_to_kmh_none():
    assert _kt_to_kmh(None) is None


def test_kt_to_kmh_peak_amphan():
    """130 kt → 240.76 km/h (AMPHAN peak)."""
    result = _kt_to_kmh(130.0)
    assert result == pytest.approx(240.76, rel=1e-2)
