"""
CycloneAI — Satellite API Endpoint Tests

Tests the /api/satellite/* endpoints:
  - GET /api/satellite/layers — list available layers
  - GET /api/satellite/tile/{layer_id}/{z}/{y}/{x} — tile proxy
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.providers.satellite import SatelliteLayersResult, SatelliteLayerInfo


@pytest.fixture
def mock_layers_result():
    """A mock SatelliteLayersResult with one available layer."""
    return SatelliteLayersResult(
        layers=[
            SatelliteLayerInfo(
                layer_id="MODIS_Terra_CorrectedReflectance_TrueColor",
                display_name="Visible (True Color)",
                channel="VIS",
                description="MODIS Terra true-color",
                instrument="MODIS / Terra",
                tile_url="https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/MODIS_Terra_CorrectedReflectance_TrueColor/default/2024-05-20/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",
                image_format="jpg",
                default_opacity=0.8,
                max_zoom=9,
                timestamp_utc="2024-05-20T00:00:00Z",
                date_label="20 May 2024",
                source="NASA GIBS / MODIS Terra",
                source_url="https://worldview.earthdata.nasa.gov/?l=MODIS_Terra_CorrectedReflectance_TrueColor",
                available=True,
                unavailable_reason=None,
            ),
        ],
        retrieved_at_utc="2024-05-21T06:00:00+00:00",
        gibs_base_url="https://gibs.earthdata.nasa.gov/wmts/epsg3857/best",
        note="Test note",
    )


@pytest.mark.asyncio
async def test_list_satellite_layers(mock_layers_result):
    """GET /api/satellite/layers returns layer list."""
    with patch(
        "app.api.satellite.get_satellite_provider"
    ) as mock_provider_fn, patch(
        "app.api.satellite.get_mosdac_provider"
    ) as mock_mosdac_provider_fn:
        mock_provider = MagicMock()
        mock_provider.get_layers = AsyncMock(return_value=mock_layers_result)
        mock_provider_fn.return_value = mock_provider
        mock_mosdac_provider_fn.return_value.is_configured = False

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/satellite/layers")

    assert resp.status_code == 200
    data = resp.json()
    assert "layers" in data
    assert len(data["layers"]) == 1
    layer = data["layers"][0]
    assert layer["layer_id"] == "MODIS_Terra_CorrectedReflectance_TrueColor"
    assert layer["channel"] == "VIS"
    assert layer["available"] is True
    assert layer["source"] == "NASA GIBS / MODIS Terra"
    assert "tile_url" in layer
    assert "{z}" in layer["tile_url"]


@pytest.mark.asyncio
async def test_list_satellite_layers_with_date(mock_layers_result):
    """GET /api/satellite/layers?date=2024-05-20 accepts a date parameter."""
    with patch(
        "app.api.satellite.get_satellite_provider"
    ) as mock_provider_fn, patch(
        "app.api.satellite.get_mosdac_provider"
    ) as mock_mosdac_provider_fn:
        mock_provider = MagicMock()
        mock_provider.get_layers = AsyncMock(return_value=mock_layers_result)
        mock_provider_fn.return_value = mock_provider
        mock_mosdac_provider_fn.return_value.is_configured = False

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/satellite/layers?date=2024-05-20")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_satellite_layers_invalid_date():
    """GET /api/satellite/layers?date=bad returns 422."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/satellite/layers?date=not-a-date")

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_satellite_disabled():
    """When satellite_enabled=False, returns empty layers list."""
    with patch("app.api.satellite.get_settings") as mock_settings:
        settings = MagicMock()
        settings.satellite_enabled = False
        mock_settings.return_value = settings

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/satellite/layers")

    assert resp.status_code == 200
    data = resp.json()
    assert data["layers"] == []
    assert "disabled" in data["note"].lower()


@pytest.mark.asyncio
async def test_mosdac_is_not_called_until_explicitly_enabled(mock_layers_result):
    """Credentials alone must not activate the optional MOSDAC integration."""
    with patch("app.api.satellite.get_settings") as mock_settings, patch(
        "app.api.satellite.get_satellite_provider"
    ) as mock_provider_fn, patch("app.api.satellite.get_mosdac_provider") as mock_mosdac_provider_fn:
        settings = MagicMock()
        settings.satellite_enabled = True
        settings.mosdac_enabled = False
        mock_settings.return_value = settings

        mock_provider = MagicMock()
        mock_provider.get_layers = AsyncMock(return_value=mock_layers_result)
        mock_provider_fn.return_value = mock_provider

        mock_mosdac = MagicMock()
        mock_mosdac.is_configured = True
        mock_mosdac_provider_fn.return_value = mock_mosdac

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/satellite/layers")

    assert resp.status_code == 200
    mock_mosdac.get_layers.assert_not_called()
    assert "MOSDAC: disabled" in resp.json()["note"]


@pytest.mark.asyncio
async def test_latest_satellite_layers_uses_layer_response(mock_layers_result):
    """GET /api/satellite/latest returns the latest dated layer metadata."""
    with patch("app.api.satellite.get_satellite_provider") as mock_provider_fn, patch(
        "app.api.satellite.get_mosdac_provider"
    ) as mock_mosdac_provider_fn:
        mock_provider = MagicMock()
        mock_provider.get_layers = AsyncMock(return_value=mock_layers_result)
        mock_provider_fn.return_value = mock_provider
        mock_mosdac_provider_fn.return_value.is_configured = False

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/satellite/latest")

    assert resp.status_code == 200
    assert resp.json()["layers"][0]["layer_id"] == "MODIS_Terra_CorrectedReflectance_TrueColor"


@pytest.mark.asyncio
async def test_tile_proxy_unknown_layer():
    """GET /api/satellite/tile/unknown/2/1/2 returns 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/satellite/tile/NONEXISTENT_LAYER/2/1/2")

    assert resp.status_code == 404
