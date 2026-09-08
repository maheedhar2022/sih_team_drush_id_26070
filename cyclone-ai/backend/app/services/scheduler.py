"""
CycloneAI — Background Scheduler (Phase 2)

Uses APScheduler to periodically refresh data from all providers.

Schedule:
  - Every 6h  : IBTrACS ACTIVE file refresh
  - Every 24h : IBTrACS NI historical update
  - Every 3h  : RSMC bulletin (when RSMC_BULLETIN_ENABLED=true)
  - On startup: immediate ingest if DB is empty or last ingest > 6h ago

Data freshness is updated in the DB on every run.
If a provider fails, the last valid DB data is retained and marked STALE.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.db.session import init_db
from app.services.ingestion import get_last_ingestion_time, ingest_all

logger = logging.getLogger("cyclone_ai.scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _run_ingest() -> None:
    """Scheduled ingest job — logs results, never raises."""
    try:
        logger.info("[Scheduler] Starting data ingestion run...")
        counts = await ingest_all()
        total = sum(counts.values())
        logger.info("[Scheduler] Ingestion complete. New observations: %s", counts)
        if total == 0:
            logger.info("[Scheduler] No new observations — data already current or no active NI storms.")
    except Exception as exc:
        logger.exception("[Scheduler] Ingestion run failed: %s", exc)


async def startup_ingest() -> None:
    """
    Run on application startup.
    Triggers an immediate ingest if:
      - The database has no observations, OR
      - The last ingest was more than 6 hours ago
    """
    settings = get_settings()

    # Ensure tables exist
    await init_db()

    last_ingest = await get_last_ingestion_time()
    threshold = timedelta(hours=settings.ibtracs_active_refresh_hours)
    now = datetime.now(timezone.utc)

    if last_ingest is None:
        logger.info("[Startup] Database empty — triggering initial ingest...")
        await _run_ingest()
    elif (now - last_ingest.replace(tzinfo=timezone.utc if last_ingest.tzinfo is None else last_ingest.tzinfo)) > threshold:
        logger.info(
            "[Startup] Last ingest was %s ago (threshold: %sh) — refreshing...",
            now - last_ingest.replace(tzinfo=timezone.utc if last_ingest.tzinfo is None else last_ingest.tzinfo),
            settings.ibtracs_active_refresh_hours
        )
        await _run_ingest()
    else:
        logger.info(
            "[Startup] Data is current (last ingest: %s). Skipping startup fetch.",
            last_ingest.isoformat()
        )


def get_scheduler() -> AsyncIOScheduler:
    """Return the global scheduler instance (creates if needed)."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def start_scheduler() -> None:
    """Configure and start the background scheduler."""
    settings = get_settings()
    scheduler = get_scheduler()

    if scheduler.running:
        return

    # IBTrACS ACTIVE: every 6 hours
    scheduler.add_job(
        _run_ingest,
        trigger=IntervalTrigger(hours=settings.ibtracs_active_refresh_hours),
        id="ibtracs_active_refresh",
        name="IBTrACS ACTIVE refresh",
        replace_existing=True,
        misfire_grace_time=600,  # 10-minute grace if missed
    )

    logger.info(
        "[Scheduler] Scheduled IBTrACS refresh every %dh",
        settings.ibtracs_active_refresh_hours,
    )

    if settings.rsmc_bulletin_enabled:
        scheduler.add_job(
            _run_ingest,
            trigger=IntervalTrigger(hours=settings.rsmc_bulletin_refresh_hours),
            id="rsmc_bulletin_refresh",
            name="RSMC Bulletin scrape",
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.info(
            "[Scheduler] Scheduled RSMC bulletin scrape every %dh",
            settings.rsmc_bulletin_refresh_hours,
        )

    scheduler.start()
    logger.info("[Scheduler] Background scheduler started.")


def stop_scheduler() -> None:
    """Stop the scheduler gracefully."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped.")
    _scheduler = None
