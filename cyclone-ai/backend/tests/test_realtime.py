"""Regression coverage for the real-time cyclone route."""
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


def test_live_positions_route_is_not_captured_as_a_cyclone_id() -> None:
    payload = {
        "count": 0,
        "positions": [],
        "server_time_utc": "2026-09-09T00:00:00+00:00",
    }
    with patch("app.api.realtime._fetch_live_positions", new=AsyncMock(return_value=payload)):
        response = TestClient(app).get("/api/cyclones/live")

    assert response.status_code == 200
    assert response.json() == payload
