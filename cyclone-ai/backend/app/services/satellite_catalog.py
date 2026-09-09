"""Satellite observation catalog and safe local asset resolution.

The catalog deliberately separates product bytes from relational metadata. It
supports the source-product pipeline while no unvalidated INSAT raster is ever
presented as a map overlay.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Optional

from sqlalchemy import desc, select

from app.config import get_settings
from app.db.models import SatelliteObservation
from app.db.session import AsyncSessionLocal


OBSERVATION_STATUSES = (
    "DISCOVERED", "DOWNLOADING", "DOWNLOADED", "PROCESSING",
    "PROCESSED", "FAILED", "UNAVAILABLE",
)


@dataclass(frozen=True)
class SatelliteStorage:
    """Creates and resolves paths under the configured satellite root only."""
    root: Path

    @classmethod
    def from_settings(cls) -> "SatelliteStorage":
        return cls(Path(get_settings().satellite_storage_dir).resolve())

    def directory(self, kind: str) -> Path:
        if kind not in {"raw", "processed", "thumbnails", "tiles"}:
            raise ValueError(f"Unsupported satellite storage kind: {kind}")
        return self.root / kind

    def relative_path(
        self, kind: str, source: str, product_id: str, observed_at: Optional[datetime], filename: str,
    ) -> str:
        safe = lambda value: re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "unknown"
        day = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        relative = Path(kind) / safe(source) / safe(product_id) / day.strftime("%Y/%m/%d") / safe(filename)
        return relative.as_posix()

    def resolve_existing(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Satellite asset path escapes the storage root") from exc
        return candidate


def observation_payload(observation: SatelliteObservation) -> dict:
    """Convert the ORM entity to source-transparent API data."""
    bbox = None
    if None not in (observation.bbox_north, observation.bbox_south, observation.bbox_east, observation.bbox_west):
        bbox = {
            "north": observation.bbox_north, "south": observation.bbox_south,
            "east": observation.bbox_east, "west": observation.bbox_west,
        }
    return {
        "id": observation.id,
        "source": observation.source,
        "source_record_id": observation.source_record_id,
        "source_filename": observation.source_filename,
        "satellite": observation.satellite,
        "sensor": observation.sensor,
        "product_id": observation.product_id,
        "product_name": observation.product_name,
        "channel": observation.channel,
        "processing_level": observation.processing_level,
        "observation_timestamp_utc": observation.observation_timestamp_utc,
        "received_at_utc": observation.received_at_utc,
        "processed_at_utc": observation.processed_at_utc,
        "bbox": bbox,
        "projection": observation.projection,
        "spatial_resolution_m": observation.spatial_resolution_m,
        "file_format": observation.file_format,
        "source_url": observation.source_url,
        "checksum_sha256": observation.checksum_sha256,
        "status": observation.status,
        "failure_reason": observation.failure_reason,
        "web_image_available": bool(observation.web_asset_path and observation.status == "PROCESSED"),
    }


async def list_observations(limit: int = 50, source: Optional[str] = None) -> list[SatelliteObservation]:
    async with AsyncSessionLocal() as session:
        query = select(SatelliteObservation).order_by(desc(SatelliteObservation.observation_timestamp_utc), desc(SatelliteObservation.id)).limit(limit)
        if source:
            query = query.where(SatelliteObservation.source == source)
        return list((await session.scalars(query)).all())


async def get_observation(observation_id: int) -> Optional[SatelliteObservation]:
    async with AsyncSessionLocal() as session:
        return await session.get(SatelliteObservation, observation_id)


async def available_channels() -> list[str]:
    async with AsyncSessionLocal() as session:
        result = await session.scalars(
            select(SatelliteObservation.channel)
            .where(SatelliteObservation.channel.is_not(None))
            .distinct()
            .order_by(SatelliteObservation.channel)
        )
        return list(result.all())


async def catalog_summary() -> dict:
    observations = await list_observations(limit=1)
    settings = get_settings()
    return {
        "satellite_enabled": settings.satellite_enabled,
        "mosdac_enabled": settings.mosdac_enabled,
        "mosdac_configured": bool(settings.mosdac_username and settings.mosdac_password),
        "storage_root_configured": bool(settings.satellite_storage_dir),
        "latest_observation_utc": observations[0].observation_timestamp_utc if observations else None,
        "catalog_state": "READY" if observations else "AWAITING_VALIDATED_SOURCE_PRODUCT",
        "note": (
            "NASA GIBS raster layers are available separately. INSAT products are listed only after "
            "MOSDAC discovery/download and product validation; no synthetic INSAT imagery is served."
        ),
    }
