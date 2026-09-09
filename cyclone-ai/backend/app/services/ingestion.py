"""
CycloneAI — Data Ingestion Service (Phase 2)

Orchestrates the full ingest pipeline:
  External Source
    ↓
  Provider (fetch)
    ↓
  Validation
    ↓
  Normalisation
    ↓
  Deduplication
    ↓
  Database (append-only)

Rules:
  - Observations are NEVER overwritten — dedup key: (cyclone_id, timestamp_utc)
  - Every observation must have: source, received_at, processed_at
  - Units normalised to km/h (wind) and hPa (pressure)
  - Coordinate bounds enforced: lat ∈ [-90,90], lon ∈ [-180,180]
  - Wind sanity: 0–400 km/h
  - Pressure sanity: 850–1050 hPa
  - Missing fields are stored as NULL, never fabricated
  - Data freshness computed from observation timestamp vs. now()
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    Cyclone as CycloneEntity,
    CycloneForecast,
    CycloneObservation,
    CycloneRecord,
    DataSource,
)
from app.db.session import AsyncSessionLocal
from app.providers.base import RawObservation, ProviderResult, ProviderStatus
from app.providers.registry import get_registry

logger = logging.getLogger("cyclone_ai.ingestion")

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------
_LAT_MIN, _LAT_MAX = -90.0, 90.0
_LON_MIN, _LON_MAX = -180.0, 180.0
_WIND_MIN_KT, _WIND_MAX_KT = 0.0, 215.0   # 215 kt ≈ 400 km/h (theoretical max)
_PRES_MIN, _PRES_MAX = 850.0, 1060.0      # hPa — reasonable TC range

# Knots → km/h conversion
_KT_TO_KMH = 1.852


def _kt_to_kmh(kt: Optional[float]) -> Optional[float]:
    if kt is None:
        return None
    return round(kt * _KT_TO_KMH, 1)


def _compute_freshness(obs_ts: datetime) -> str:
    """
    Determine data freshness based on observation timestamp vs. now.
    Returns: LIVE | DELAYED | STALE | HISTORICAL
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    age_hours = (now - obs_ts).total_seconds() / 3600

    if age_hours <= settings.data_live_threshold_hours:
        return "LIVE"
    if age_hours <= settings.data_delayed_threshold_hours:
        return "DELAYED"
    # Anything older than 1 year is HISTORICAL
    if age_hours > 24 * 365:
        return "HISTORICAL"
    return "STALE"


def _validate_obs(obs: RawObservation) -> list[str]:
    """
    Validate a raw observation. Returns list of error strings.
    Empty list = valid.
    """
    errors: list[str] = []

    if not (-90 <= obs.latitude <= 90):
        errors.append(f"latitude {obs.latitude} out of range")
    if not (-180 <= obs.longitude <= 180):
        errors.append(f"longitude {obs.longitude} out of range")
    if obs.timestamp_utc.tzinfo is None:
        errors.append("timestamp_utc is not timezone-aware")
    if obs.wind_speed is not None:
        if not (_WIND_MIN_KT <= obs.wind_speed <= _WIND_MAX_KT):
            errors.append(f"wind_speed {obs.wind_speed} kt out of sanity range")
    if obs.central_pressure is not None:
        if not (_PRES_MIN <= obs.central_pressure <= _PRES_MAX):
            errors.append(f"central_pressure {obs.central_pressure} hPa out of range")
    if not obs.source:
        errors.append("source attribution missing")
    if not obs.cyclone_id:
        errors.append("cyclone_id missing")

    return errors


def _validate_forecast(forecast) -> list[str]:
    """Validate an official forecast point before persisting it."""
    errors: list[str] = []

    if not forecast.cyclone_id:
        errors.append("cyclone_id missing")
    if not forecast.source:
        errors.append("source attribution missing")
    if not (-90 <= forecast.latitude <= 90):
        errors.append(f"latitude {forecast.latitude} out of range")
    if not (-180 <= forecast.longitude <= 180):
        errors.append(f"longitude {forecast.longitude} out of range")
    if forecast.issued_at_utc.tzinfo is None or forecast.valid_at_utc.tzinfo is None:
        errors.append("forecast timestamps must be timezone-aware")
    elif forecast.valid_at_utc < forecast.issued_at_utc:
        errors.append("forecast valid time precedes issue time")
    if forecast.forecast_hour < 0:
        errors.append("forecast hour must be non-negative")

    return errors


def _normalise(obs: RawObservation, processed_at: datetime) -> CycloneObservation:
    """
    Convert a validated RawObservation → normalised CycloneObservation.
    Units: wind_speed_kmh, pressure_hpa.
    """
    # Convert wind to km/h
    if obs.wind_unit == "kt":
        wind_kmh = _kt_to_kmh(obs.wind_speed)
    elif obs.wind_unit in ("kmh", "km/h"):
        wind_kmh = obs.wind_speed
    elif obs.wind_unit == "m/s":
        wind_kmh = round(obs.wind_speed * 3.6, 1) if obs.wind_speed else None
    else:
        wind_kmh = _kt_to_kmh(obs.wind_speed)  # assume kt as safe default

    return CycloneObservation(
        cyclone_id=obs.cyclone_id,
        cyclone_name=obs.cyclone_name,
        basin=obs.basin,
        timestamp_utc=obs.timestamp_utc,
        latitude=obs.latitude,
        longitude=obs.longitude,
        wind_speed_kmh=wind_kmh,
        pressure_hpa=obs.central_pressure,
        intensity_category=obs.intensity_category,
        movement_direction=obs.movement_direction,
        movement_speed_kmh=obs.movement_speed,
        source=obs.source,
        source_url=obs.source_url,
        received_at_utc=obs.received_at_utc,
        processed_at_utc=processed_at,
        data_freshness=_compute_freshness(obs.timestamp_utc),
    )


async def _upsert_data_source(session: AsyncSession, provider_name: str,
                               display_name: str, url: Optional[str],
                               status: str, error: Optional[str]) -> None:
    """Update or insert a data_sources row."""
    result = await session.execute(
        select(DataSource).where(DataSource.name == provider_name)
    )
    src = result.scalar_one_or_none()

    if src is None:
        src = DataSource(
            name=provider_name,
            display_name=display_name,
            url=url,
            auth_type="none",
        )
        session.add(src)

    src.last_fetched_utc = datetime.now(timezone.utc)
    src.last_status = status
    src.last_error = error


async def _upsert_cyclone(session: AsyncSession, obs: RawObservation) -> None:
    """Create or refresh cyclone identity metadata without touching observations."""
    result = await session.execute(
        select(CycloneEntity).where(CycloneEntity.cyclone_id == obs.cyclone_id)
    )
    cyclone = result.scalar_one_or_none()

    if cyclone is None:
        session.add(CycloneEntity(
            cyclone_id=obs.cyclone_id,
            cyclone_name=obs.cyclone_name,
            basin=obs.basin,
            status="ACTIVE",
            source=obs.source,
            source_id=obs.cyclone_id,
        ))
        return

    cyclone.cyclone_name = obs.cyclone_name
    cyclone.basin = obs.basin
    cyclone.status = "ACTIVE"
    cyclone.source = obs.source


async def ingest_all() -> dict[str, int]:
    """
    Main ingestion entry point. Fetch from all providers and persist.
    Returns dict of {provider_name: observations_inserted}.
    """
    registry = get_registry()
    results = await registry.fetch_all()
    processed_at = datetime.now(timezone.utc)

    counts: dict[str, int] = {}

    async with AsyncSessionLocal() as session:
        for result in results:
            provider_name = result.provider_name
            inserted = 0

            # Update data_source registry
            await _upsert_data_source(
                session,
                provider_name=provider_name,
                display_name=provider_name,
                url=result.source_url,
                status=result.status.value,
                error=result.error_message,
            )

            if result.status not in (ProviderStatus.OK, ProviderStatus.STALE):
                logger.warning(
                    "Provider %s returned status %s: %s",
                    provider_name, result.status, result.error_message
                )
                counts[provider_name] = 0
                continue

            # Process each observation
            for obs in result.observations:
                errors = _validate_obs(obs)
                if errors:
                    logger.warning(
                        "Validation failed for %s@%s: %s",
                        obs.cyclone_id, obs.timestamp_utc, errors
                    )
                    continue

                await _upsert_cyclone(session, obs)

                # Write raw record (audit log) — ignore conflict
                raw_rec = CycloneRecord(
                    sid=obs.cyclone_id,
                    cyclone_name=obs.cyclone_name,
                    basin=obs.basin,
                    timestamp_utc=obs.timestamp_utc,
                    latitude=obs.latitude,
                    longitude=obs.longitude,
                    wind_speed=obs.wind_speed,
                    wind_unit=obs.wind_unit,
                    central_pressure=obs.central_pressure,
                    intensity_category=obs.intensity_category,
                    movement_direction=obs.movement_direction,
                    movement_speed=obs.movement_speed,
                    source=obs.source,
                    source_url=obs.source_url,
                    received_at_utc=obs.received_at_utc,
                    processed_at_utc=processed_at,
                    raw_data=obs.raw_data,
                )
                try:
                    session.add(raw_rec)
                    await session.flush()
                except Exception:
                    await session.rollback()
                    # Duplicate — expected and fine

                # Write normalised observation (dedup by cyclone_id + ts)
                norm = _normalise(obs, processed_at)
                existing = await session.execute(
                    select(CycloneObservation).where(
                        CycloneObservation.cyclone_id == norm.cyclone_id,
                        CycloneObservation.timestamp_utc == norm.timestamp_utc,
                    )
                )
                if existing.scalar_one_or_none() is None:
                    session.add(norm)
                    try:
                        await session.flush()
                        inserted += 1
                    except Exception:
                        await session.rollback()

            # Persist official forecast points separately from observed tracks.
            for forecast in result.forecasts:
                errors = _validate_forecast(forecast)
                if errors:
                    logger.warning(
                        "Forecast validation failed for %s@%s: %s",
                        forecast.cyclone_id,
                        forecast.valid_at_utc,
                        errors,
                    )
                    continue

                existing_forecast = await session.execute(
                    select(CycloneForecast).where(
                        CycloneForecast.cyclone_id == forecast.cyclone_id,
                        CycloneForecast.issued_at_utc == forecast.issued_at_utc,
                        CycloneForecast.valid_at_utc == forecast.valid_at_utc,
                    )
                )
                if existing_forecast.scalar_one_or_none() is not None:
                    continue

                session.add(CycloneForecast(
                    cyclone_id=forecast.cyclone_id,
                    cyclone_name=forecast.cyclone_name,
                    issued_at_utc=forecast.issued_at_utc,
                    valid_at_utc=forecast.valid_at_utc,
                    forecast_hour=forecast.forecast_hour,
                    latitude=forecast.latitude,
                    longitude=forecast.longitude,
                    wind_speed_kmh=forecast.wind_speed_kmh,
                    pressure_hpa=forecast.pressure_hpa,
                    intensity_category=forecast.intensity_category,
                    source=forecast.source,
                    source_url=forecast.source_url,
                    received_at_utc=forecast.received_at_utc,
                ))

            counts[provider_name] = inserted
            logger.info("Provider %s: %d new observations inserted", provider_name, inserted)

        await session.commit()

    return counts


async def get_active_ni_storms(max_age_hours: int = 48) -> list[CycloneObservation]:
    """
    Return the most recent observation per cyclone for active NI storms.
    'Active' = an observation exists within max_age_hours.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CycloneObservation)
            .where(
                CycloneObservation.basin == "NI",
                CycloneObservation.timestamp_utc >= cutoff,
            )
            .order_by(
                CycloneObservation.cyclone_id,
                CycloneObservation.timestamp_utc.desc(),
            )
        )
        rows = result.scalars().all()

    # Keep only the latest per cyclone
    seen: dict[str, CycloneObservation] = {}
    for obs in rows:
        if obs.cyclone_id not in seen:
            seen[obs.cyclone_id] = obs

    return list(seen.values())


async def get_cyclone_track(cyclone_id: str) -> list[CycloneObservation]:
    """Return all observations for a specific cyclone, ordered by time."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CycloneObservation)
            .where(CycloneObservation.cyclone_id == cyclone_id)
            .order_by(CycloneObservation.timestamp_utc)
        )
        return result.scalars().all()


async def get_latest_cyclone_forecast(cyclone_id: str) -> list[CycloneForecast]:
    """Return all points for the most recently issued official forecast."""
    async with AsyncSessionLocal() as session:
        latest_issue_result = await session.execute(
            select(CycloneForecast.issued_at_utc)
            .where(CycloneForecast.cyclone_id == cyclone_id)
            .order_by(CycloneForecast.issued_at_utc.desc())
            .limit(1)
        )
        latest_issue = latest_issue_result.scalar_one_or_none()
        if latest_issue is None:
            return []

        result = await session.execute(
            select(CycloneForecast)
            .where(
                CycloneForecast.cyclone_id == cyclone_id,
                CycloneForecast.issued_at_utc == latest_issue,
            )
            .order_by(CycloneForecast.valid_at_utc)
        )
        return result.scalars().all()


async def get_data_sources() -> list[DataSource]:
    """Return all registered data sources."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(DataSource))
        return result.scalars().all()


async def get_last_ingestion_time() -> Optional[datetime]:
    """Return the most recent processed_at across all observations (always UTC-aware)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(CycloneObservation.processed_at_utc)
            .order_by(CycloneObservation.processed_at_utc.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        # SQLite returns naive datetimes — normalise to UTC
        if row.tzinfo is None:
            return row.replace(tzinfo=timezone.utc)
        return row
