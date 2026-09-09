"""
CycloneAI — Cyclones API tests
"""
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.main import app

client = TestClient(app)

DEMO_CYCLONE_ID = "AMPHAN_2020_NI"


def test_active_cyclones_returns_200():
    response = client.get("/api/cyclones/active")
    assert response.status_code == 200


def test_active_cyclones_schema():
    response = client.get("/api/cyclones/active")
    data = response.json()
    assert "data_mode" in data
    assert "count" in data
    assert "cyclones" in data
    assert isinstance(data["cyclones"], list)


def test_active_cyclones_returns_503_when_database_is_unavailable():
    """A database failure must not be disguised as historical cyclone data."""
    with patch(
        "app.api.cyclones.get_active_ni_storms",
        new=AsyncMock(side_effect=RuntimeError("database unavailable")),
    ):
        response = client.get("/api/cyclones/active")

    assert response.status_code == 503
    assert "temporarily unavailable" in response.json()["detail"]


def test_historical_or_demo_mode_is_labeled():
    """
    Phase 2: fallback to verified historical data returns HISTORICAL (not DEMO).
    Both DEMO and HISTORICAL are acceptable non-live modes — both must be explicit.
    """
    response = client.get("/api/cyclones/active")
    data = response.json()
    valid_modes = {"DEMO", "HISTORICAL", "LIVE", "DELAYED"}
    for cyclone in data["cyclones"]:
        assert cyclone["data_mode"] in valid_modes, (
            f"Cyclone {cyclone['id']} has unexpected data_mode: {cyclone['data_mode']}"
        )


def test_cyclone_detail_returns_200():
    response = client.get(f"/api/cyclones/{DEMO_CYCLONE_ID}")
    assert response.status_code == 200


def test_cyclone_detail_schema():
    response = client.get(f"/api/cyclones/{DEMO_CYCLONE_ID}")
    data = response.json()
    required = ["id", "name", "basin", "status", "data_mode", "latitude", "longitude"]
    for field in required:
        assert field in data, f"Missing field: {field}"


def test_cyclone_detail_not_found():
    response = client.get("/api/cyclones/NONEXISTENT_CYCLONE")
    assert response.status_code == 404


def test_cyclone_track_returns_200():
    response = client.get(f"/api/cyclones/{DEMO_CYCLONE_ID}/track")
    assert response.status_code == 200


def test_cyclone_track_has_points():
    response = client.get(f"/api/cyclones/{DEMO_CYCLONE_ID}/track")
    data = response.json()
    assert "points" in data
    assert len(data["points"]) > 0


def test_cyclone_track_point_schema():
    response = client.get(f"/api/cyclones/{DEMO_CYCLONE_ID}/track")
    data = response.json()
    point = data["points"][0]
    assert "timestamp" in point
    assert "latitude" in point
    assert "longitude" in point


def test_cyclone_forecast_returns_persisted_official_points():
    issued_at = datetime.now(timezone.utc)
    row = SimpleNamespace(
        cyclone_id=DEMO_CYCLONE_ID,
        cyclone_name="AMPHAN",
        issued_at_utc=issued_at,
        valid_at_utc=issued_at + timedelta(hours=6),
        forecast_hour=6,
        latitude=15.0,
        longitude=86.8,
        wind_speed_kmh=185.0,
        pressure_hpa=940.0,
        intensity_category="Extremely Severe Cyclonic Storm",
        source="RSMC New Delhi",
        source_url="https://example.com/bulletin",
    )
    with patch(
        "app.api.cyclones.get_latest_cyclone_forecast",
        new=AsyncMock(return_value=[row]),
    ):
        response = client.get(f"/api/cyclones/{DEMO_CYCLONE_ID}/forecast")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "RSMC New Delhi"
    assert data["points"][0]["forecast_hour"] == 6


def test_latitude_in_valid_range():
    response = client.get(f"/api/cyclones/{DEMO_CYCLONE_ID}/track")
    data = response.json()
    for point in data["points"]:
        assert -90.0 <= point["latitude"] <= 90.0
        assert -180.0 <= point["longitude"] <= 180.0


def test_cyclone_coordinates_valid():
    response = client.get(f"/api/cyclones/{DEMO_CYCLONE_ID}")
    data = response.json()
    assert -90.0 <= data["latitude"] <= 90.0
    assert -180.0 <= data["longitude"] <= 180.0
