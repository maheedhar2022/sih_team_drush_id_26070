"""
CycloneAI — Health endpoint tests
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_schema():
    response = client.get("/api/health")
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "demo_mode" in data
    assert "device" in data
    assert "timestamp_utc" in data
    assert "data_mode" in data


def test_health_status_is_online():
    response = client.get("/api/health")
    data = response.json()
    assert data["status"] == "ONLINE"


def test_health_demo_mode_is_bool():
    response = client.get("/api/health")
    data = response.json()
    assert isinstance(data["demo_mode"], bool)


def test_health_sources_present():
    response = client.get("/api/health")
    data = response.json()
    assert "sources" in data
    assert isinstance(data["sources"], dict)


def test_root_redirect():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "CycloneAI API"
