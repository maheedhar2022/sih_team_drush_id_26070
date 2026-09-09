"""Focused tests for Phase 3 satellite catalog boundaries."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.satellite_catalog import SatelliteStorage


def test_satellite_storage_uses_stable_source_product_date_layout(tmp_path: Path):
    storage = SatelliteStorage(tmp_path)
    path = storage.relative_path(
        "raw",
        "MOSDAC/ISRO",
        "3SIMG_L1B_STD",
        datetime(2026, 9, 9, 6, tzinfo=timezone.utc),
        "INSAT 3DS L1B.h5",
    )

    assert path == "raw/MOSDAC_ISRO/3SIMG_L1B_STD/2026/09/09/INSAT_3DS_L1B.h5"
    assert storage.resolve_existing(path) == tmp_path / Path(path)


def test_satellite_storage_rejects_paths_outside_root(tmp_path: Path):
    storage = SatelliteStorage(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        storage.resolve_existing("../../outside.png")


@pytest.mark.asyncio
async def test_satellite_catalog_status_does_not_expose_configuration_secrets():
    summary = {
        "satellite_enabled": True,
        "mosdac_enabled": False,
        "mosdac_configured": True,
        "storage_root_configured": True,
        "latest_observation_utc": None,
        "catalog_state": "AWAITING_VALIDATED_SOURCE_PRODUCT",
        "note": "No synthetic imagery is served.",
    }
    with patch("app.api.satellite.catalog_summary", new=AsyncMock(return_value=summary)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/satellite/status")

    assert response.status_code == 200
    data = response.json()
    assert data["catalog_state"] == "AWAITING_VALIDATED_SOURCE_PRODUCT"
    assert "password" not in data
    assert "username" not in data


@pytest.mark.asyncio
async def test_missing_processed_image_is_an_explicit_404():
    with patch("app.api.satellite.get_observation", new=AsyncMock(return_value=None)):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/satellite/observations/999/image")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
