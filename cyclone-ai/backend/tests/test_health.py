"""
CycloneAI — Health endpoint tests (Phase 2 updated)
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_schema_phase2():
    """Health response must include Phase 2 fields."""
    response = client.get("/api/health")
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "demo_mode" in data
    assert "device" in data
    assert "timestamp_utc" in data
    assert "data_mode" in data
    # Phase 2 additions
    assert "provider_statuses" in data
    assert "active_ni_storms" in data
    assert isinstance(data["active_ni_storms"], int)
    assert isinstance(data["provider_statuses"], dict)


def test_health_status_is_online():
    response = client.get("/api/health")
    data = response.json()
    assert data["status"] in ("ONLINE", "DEGRADED", "OFFLINE")


def test_health_demo_mode_is_bool():
    response = client.get("/api/health")
    data = response.json()
    assert isinstance(data["demo_mode"], bool)


def test_health_sources_present():
    response = client.get("/api/health")
    data = response.json()
    assert "sources" in data
    assert isinstance(data["sources"], dict)
    assert "ibtracs" in data["sources"]


def test_health_version_is_phase2():
    response = client.get("/api/health")
    data = response.json()
    assert "phase2" in data["version"] or "0.2" in data["version"]


def test_root_redirect():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "CycloneAI API"
    assert "phase" in data


def test_cyclones_active_returns_data():
    """Active cyclones endpoint returns valid response structure."""
    response = client.get("/api/cyclones/active")
    assert response.status_code == 200
    data = response.json()
    assert "data_mode" in data
    assert "data_freshness" in data
    assert "count" in data
    assert "cyclones" in data
    assert isinstance(data["cyclones"], list)
    assert "source" in data


def test_cyclones_active_has_freshness():
    """Response must include data_freshness — never silently omit."""
    response = client.get("/api/cyclones/active")
    data = response.json()
    assert data["data_freshness"] in ("LIVE", "DELAYED", "STALE", "HISTORICAL", "DEMO")


def test_cyclones_active_note_indicates_mode():
    """When in HISTORICAL mode, note must say so explicitly."""
    response = client.get("/api/cyclones/active")
    data = response.json()
    if data["data_mode"] == "HISTORICAL":
        assert data["note"] is not None
        assert "HISTORICAL" in data["note"]


def test_cyclone_source_always_present():
    """Every cyclone in the response must have a non-empty source."""
    response = client.get("/api/cyclones/active")
    data = response.json()
    for cyclone in data["cyclones"]:
        assert "source" in cyclone
        assert cyclone["source"]  # non-empty


def test_sources_endpoint_exists():
    """Data sources registry endpoint must be available."""
    response = client.get("/api/cyclones/sources/list")
    assert response.status_code == 200
    data = response.json()
    assert "sources" in data
    assert "retrieved_at_utc" in data


def test_forecast_unavailable_returns_404():
    """Forecast endpoint returns 404 when no forecast data available — not fake data."""
    response = client.get("/api/cyclones/AMPHAN_2020_NI/forecast")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
