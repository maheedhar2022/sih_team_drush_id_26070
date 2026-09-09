"""Public data-source registry endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.cyclones import list_data_sources
from app.schemas.cyclone import DataSourcesResponse


router = APIRouter(prefix="/api", tags=["data sources"])


@router.get(
    "/data-sources",
    response_model=DataSourcesResponse,
    summary="List meteorological data sources and their status",
)
async def list_data_sources_endpoint() -> DataSourcesResponse:
    """Expose source provenance at the documented top-level path."""
    return await list_data_sources()
