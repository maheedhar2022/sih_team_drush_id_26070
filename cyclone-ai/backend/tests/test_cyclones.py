"""
CycloneAI — Cyclones API tests
"""
import pytest
from fastapi.testclient import TestClient

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
