"""MOSDAC discovery and source-product download orchestration.

The provider owns HTTP details; this service owns persistence, deduplication,
and storage paths. Products remain ``DOWNLOADED`` until a real source HDF
sample is inspected and a format-specific processor is implemented.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from app.config import get_settings
from app.db.models import DataSource, SatelliteObservation
from app.db.session import AsyncSessionLocal
from app.providers.mosdac import MOSDAC_DATASETS, MOSDACSearchResult, get_mosdac_provider
from app.services.satellite_catalog import SatelliteStorage


class MOSDACIntegrationError(RuntimeError):
    """A controlled error safe to return from the satellite API."""


@dataclass(frozen=True)
class MOSDACDiscoverySummary:
    dataset_id: str
    discovered_count: int
    inserted_count: int
    updated_count: int


def _source_record_to_observation(entry: MOSDACSearchResult, dataset_id: str) -> dict:
    dataset = MOSDAC_DATASETS[dataset_id]
    suffix = Path(entry.identifier).suffix.lower().lstrip(".") or None
    return {
        "source": "MOSDAC",
        "source_record_id": entry.record_id,
        "source_filename": entry.identifier,
        "satellite": dataset["satellite"],
        "sensor": dataset["sensor"],
        "product_id": dataset_id,
        "product_name": dataset["description"],
        # The L1B source granule contains multiple channels. A specific channel
        # is recorded only after product metadata is inspected.
        "channel": None,
        "processing_level": "L1B",
        "observation_timestamp_utc": entry.observation_start_utc,
        "bbox_north": entry.bbox_north,
        "bbox_south": entry.bbox_south,
        "bbox_east": entry.bbox_east,
        "bbox_west": entry.bbox_west,
        "file_format": suffix,
        "source_url": "https://www.mosdac.gov.in/catalog-app/satellite.php",
    }


async def _record_source_status(session, status: str, error: Optional[str] = None) -> None:
    source = await session.scalar(select(DataSource).where(DataSource.name == "mosdac"))
    if source is None:
        source = DataSource(
            name="mosdac",
            display_name="MOSDAC / ISRO INSAT",
            url="https://www.mosdac.gov.in/downloadapi-manual",
            auth_type="credentials",
            update_frequency="source-dependent",
            enabled=True,
        )
        session.add(source)
    source.last_fetched_utc = datetime.now(timezone.utc)
    source.last_status = status
    source.last_error = error


async def discover_mosdac_products(
    target_date: Optional[datetime] = None, limit: int = 5,
) -> MOSDACDiscoverySummary:
    """Search official MOSDAC catalog and persist exact source granule metadata."""
    settings = get_settings()
    if not settings.mosdac_enabled:
        raise MOSDACIntegrationError("MOSDAC is disabled. Set MOSDAC_ENABLED=true to enable source discovery.")

    provider = get_mosdac_provider()
    dataset_id, entries = await provider.discover_products(target_date=target_date, count=limit)
    if not dataset_id:
        async with AsyncSessionLocal() as session:
            await _record_source_status(session, "unavailable", "No matching INSAT-3DS or INSAT-3DR source granules found.")
            await session.commit()
        return MOSDACDiscoverySummary("", 0, 0, 0)

    inserted_count = 0
    updated_count = 0
    async with AsyncSessionLocal() as session:
        for entry in entries:
            values = _source_record_to_observation(entry, dataset_id)
            observation = await session.scalar(
                select(SatelliteObservation).where(
                    SatelliteObservation.source == "MOSDAC",
                    SatelliteObservation.source_record_id == entry.record_id,
                )
            )
            if observation is None:
                session.add(SatelliteObservation(**values, status="DISCOVERED"))
                inserted_count += 1
                continue

            # Refresh source metadata while preserving the product's download
            # and processing audit fields.
            for field, value in values.items():
                setattr(observation, field, value)
            updated_count += 1

        await _record_source_status(session, "ok")
        await session.commit()

    return MOSDACDiscoverySummary(dataset_id, len(entries), inserted_count, updated_count)


async def download_mosdac_observation(observation_id: int) -> SatelliteObservation:
    """Download a previously discovered granule using the official MOSDAC API."""
    settings = get_settings()
    if not settings.mosdac_enabled or not settings.mosdac_download_enabled:
        raise MOSDACIntegrationError(
            "MOSDAC downloads are disabled. Set MOSDAC_ENABLED=true and MOSDAC_DOWNLOAD_ENABLED=true."
        )

    async with AsyncSessionLocal() as session:
        observation = await session.get(SatelliteObservation, observation_id)
        if observation is None:
            raise MOSDACIntegrationError("Satellite observation not found.")
        if observation.source != "MOSDAC":
            raise MOSDACIntegrationError("Only MOSDAC catalog observations can be downloaded here.")
        if observation.status in {"DOWNLOADED", "PROCESSING", "PROCESSED"} and observation.raw_file_path:
            return observation

        filename = observation.source_filename
        if not filename:
            raise MOSDACIntegrationError("MOSDAC source filename is missing; product was not downloaded.")
        storage = SatelliteStorage.from_settings()
        relative_path = storage.relative_path(
            "raw", observation.source, observation.product_id, observation.observation_timestamp_utc, filename,
        )
        destination = storage.resolve_existing(relative_path)
        observation.status = "DOWNLOADING"
        observation.failure_reason = None
        await session.commit()

    try:
        result = await get_mosdac_provider().download_record(observation.source_record_id, destination)
    except Exception as exc:
        async with AsyncSessionLocal() as session:
            failed = await session.get(SatelliteObservation, observation_id)
            if failed is not None:
                failed.status = "FAILED"
                failed.failure_reason = str(exc)
                await _record_source_status(session, "error", "MOSDAC product download failed.")
                await session.commit()
        raise MOSDACIntegrationError(str(exc)) from exc

    async with AsyncSessionLocal() as session:
        completed = await session.get(SatelliteObservation, observation_id)
        if completed is None:
            raise MOSDACIntegrationError("Satellite observation disappeared during download.")
        completed.raw_file_path = relative_path
        completed.checksum_sha256 = result.checksum_sha256
        completed.status = "DOWNLOADED"
        completed.processed_at_utc = None
        completed.failure_reason = None
        await _record_source_status(session, "ok")
        await session.commit()
        return completed
