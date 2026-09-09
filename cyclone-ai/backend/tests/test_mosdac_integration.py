"""Tests for official MOSDAC discovery and guarded integration endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.providers.mosdac import MOSDACSearchResult
from app.services.mosdac_ingestion import (
    MOSDACDiscoverySummary,
    MOSDACIntegrationError,
    _source_record_to_observation,
)
from app.services.scheduler import _run_mosdac_discovery


def test_mosdac_source_entry_uses_actual_catalog_metadata():
    entry = MOSDACSearchResult(
        record_id="18384978",
        identifier="3SIMG_09SEP2026_0900_L1B_STD_V01R00.h5",
        updated="2026-09-09T09:00:00Z",
        dataset_id="3SIMG_L1B_STD",
        observation_start_utc=datetime(2026, 9, 9, 9, tzinfo=timezone.utc),
        observation_end_utc=datetime(2026, 9, 9, 9, 30, tzinfo=timezone.utc),
        bbox_north=81.04,
        bbox_south=-81.04,
        bbox_east=163.15,
        bbox_west=0.84,
    )

    observation = _source_record_to_observation(entry, "3SIMG_L1B_STD")

    assert observation["satellite"] == "INSAT-3DS"
    assert observation["source_record_id"] == "18384978"
    assert observation["source_filename"].endswith(".h5")
    assert observation["observation_timestamp_utc"] == entry.observation_start_utc
    assert observation["channel"] is None


@pytest.mark.asyncio
async def test_mosdac_discovery_requires_admin_token():
    settings = MagicMock(satellite_admin_token="test-admin-token")
    with patch("app.api.satellite.get_settings", return_value=settings):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/satellite/mosdac/discover")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_mosdac_discovery_catalogs_source_products_without_download():
    settings = MagicMock(satellite_admin_token="test-admin-token")
    summary = MOSDACDiscoverySummary(
        dataset_id="3SIMG_L1B_STD", discovered_count=2, inserted_count=1, updated_count=1,
    )
    with patch("app.api.satellite.get_settings", return_value=settings), patch(
        "app.api.satellite.discover_mosdac_products", new=AsyncMock(return_value=summary),
    ) as discover:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/satellite/mosdac/discover?date=2026-09-09&limit=2",
                headers={"X-Satellite-Admin-Token": "test-admin-token"},
            )

    assert response.status_code == 200
    assert response.json()["dataset_id"] == "3SIMG_L1B_STD"
    assert response.json()["inserted_count"] == 1
    discover.assert_awaited_once()


@pytest.mark.asyncio
async def test_mosdac_discovery_reports_disabled_source_cleanly():
    settings = MagicMock(satellite_admin_token="test-admin-token")
    with patch("app.api.satellite.get_settings", return_value=settings), patch(
        "app.api.satellite.discover_mosdac_products",
        new=AsyncMock(side_effect=MOSDACIntegrationError("MOSDAC is disabled.")),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/satellite/mosdac/discover",
                headers={"X-Satellite-Admin-Token": "test-admin-token"},
            )

    assert response.status_code == 503
    assert "disabled" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_scheduler_discovery_is_metadata_only():
    summary = MOSDACDiscoverySummary(
        dataset_id="3SIMG_L1B_STD", discovered_count=1, inserted_count=1, updated_count=0,
    )
    with patch(
        "app.services.scheduler.discover_mosdac_products",
        new=AsyncMock(return_value=summary),
    ) as discover:
        await _run_mosdac_discovery()

    discover.assert_awaited_once_with(limit=5)
