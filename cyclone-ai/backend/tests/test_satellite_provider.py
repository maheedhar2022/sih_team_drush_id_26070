"""
CycloneAI — Satellite Provider Unit Tests

Tests the GIBS satellite provider:
  - URL template construction
  - Layer discovery and metadata
  - Availability flag propagation
  - Date handling (default to yesterday)
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.providers.satellite import (
    SatelliteProvider,
    GIBS_LAYERS,
    SatelliteLayerInfo,
    SatelliteLayersResult,
    GIBSLayerDef,
)


class TestGIBSLayerDefinitions:
    """Test that GIBS layer definitions are well-formed."""

    def test_all_layers_have_required_fields(self):
        for layer in GIBS_LAYERS:
            assert layer.layer_id, "layer_id must be non-empty"
            assert layer.display_name, "display_name must be non-empty"
            assert layer.channel in ("VIS", "IR", "WV"), f"Invalid channel: {layer.channel}"
            assert layer.image_format in ("png", "jpg"), f"Invalid format: {layer.image_format}"
            assert 0 < layer.default_opacity <= 1.0
            assert layer.max_zoom > 0
            assert layer.attribution, "attribution must be non-empty"

    def test_at_least_one_visible_and_infrared_layer(self):
        channels = {l.channel for l in GIBS_LAYERS}
        assert "VIS" in channels, "Must have at least one VIS layer"
        assert "IR" in channels, "Must have at least one IR layer"

    def test_unique_layer_ids(self):
        ids = [l.layer_id for l in GIBS_LAYERS]
        assert len(ids) == len(set(ids)), "Layer IDs must be unique"


class TestSatelliteProvider:
    """Test the SatelliteProvider class."""

    def _make_provider(self):
        with patch("app.providers.satellite.get_settings") as mock_settings:
            settings = MagicMock()
            settings.gibs_wmts_url = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"
            mock_settings.return_value = settings
            return SatelliteProvider()

    def test_tile_url_construction(self):
        provider = self._make_provider()
        layer = GIBS_LAYERS[0]  # MODIS Terra TrueColor
        url = provider._tile_url(layer, "2024-05-20")
        assert "2024-05-20" in url
        assert layer.layer_id in url
        assert "{z}" in url
        assert "{y}" in url
        assert "{x}" in url
        assert url.endswith(f".{layer.image_format}")

    def test_source_url_contains_layer_id(self):
        provider = self._make_provider()
        layer = GIBS_LAYERS[0]
        url = provider._source_url(layer)
        assert "worldview.earthdata.nasa.gov" in url
        assert layer.layer_id in url

    @pytest.mark.asyncio
    async def test_get_layers_returns_all_defined_layers(self):
        provider = self._make_provider()
        target = datetime(2024, 5, 20, tzinfo=timezone.utc)

        # Mock all tile checks as available
        with patch.object(provider, "check_tile_available", return_value=(True, None)):
            result = await provider.get_layers(target_date=target)

        assert isinstance(result, SatelliteLayersResult)
        assert len(result.layers) == len(GIBS_LAYERS)
        assert "20 May 2024" in result.note

        for info in result.layers:
            assert info.available is True
            assert info.unavailable_reason is None
            assert info.source  # attribution present
            assert "2024-05-20" in info.timestamp_utc

    @pytest.mark.asyncio
    async def test_get_layers_marks_unavailable(self):
        provider = self._make_provider()
        target = datetime(2024, 5, 20, tzinfo=timezone.utc)

        # Mock all tile checks as unavailable
        with patch.object(
            provider, "check_tile_available",
            return_value=(False, "HTTP 404"),
        ):
            result = await provider.get_layers(target_date=target)

        for info in result.layers:
            assert info.available is False
            assert info.unavailable_reason == "HTTP 404"

    @pytest.mark.asyncio
    async def test_get_layers_default_date_is_yesterday(self):
        provider = self._make_provider()
        now = datetime.now(timezone.utc)
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        with patch.object(provider, "check_tile_available", return_value=(True, None)):
            result = await provider.get_layers(target_date=None)

        # At least one layer should have yesterday's date
        assert any(yesterday in l.timestamp_utc for l in result.layers)

    @pytest.mark.asyncio
    async def test_check_tile_available_handles_network_error(self):
        provider = self._make_provider()
        layer = GIBS_LAYERS[0]

        import httpx
        with patch("httpx.AsyncClient") as mock_client:
            session = MagicMock()
            session.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))
            mock_client.return_value.__aenter__ = AsyncMock(return_value=session)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)

            available, reason = await provider.check_tile_available(layer, "2024-05-20")

        assert available is False
        assert reason is not None
