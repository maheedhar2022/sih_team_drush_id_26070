"""
CycloneAI Backend — Application Configuration (Phase 4)
Reads settings from environment variables / .env file.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── General ──────────────────────────────────────────────────────────────
    app_env: str = "development"
    app_version: str = "0.4.0-phase4"
    demo_mode: bool = True   # Falls back to historical if no live data found

    # CORS — accepts a comma-separated string or a JSON list
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # ── Database ──────────────────────────────────────────────────────────────
    # SQLite (dev/default): sqlite+aiosqlite:///./cycloneai.db
    # PostgreSQL (prod):    postgresql+asyncpg://user:pass@host:5432/cycloneai
    database_url: str = "sqlite+aiosqlite:///./cycloneai.db"

    # ── Cache (optional) ─────────────────────────────────────────────────────
    redis_url: str = ""

    # ── IBTrACS Provider ─────────────────────────────────────────────────────
    # Public NOAA NCEI endpoint — no authentication required
    ibtracs_base_url: str = (
        "https://www.ncei.noaa.gov/data/international-best-track-archive"
        "-for-climate-stewardship-ibtracs/v04r01/access/csv/"
    )
    ibtracs_active_file: str = "ibtracs.ACTIVE.list.v04r01.csv"
    ibtracs_ni_file: str = "ibtracs.NI.list.v04r01.csv"
    # Refresh intervals (hours)
    ibtracs_active_refresh_hours: int = 6
    ibtracs_historical_refresh_hours: int = 24

    # ── RSMC Bulletin Scraper ─────────────────────────────────────────────────
    # Disabled by default — bulletin parsing is fragile (text-based)
    rsmc_bulletin_enabled: bool = False
    rsmc_bulletin_url: str = "https://rsmcnewdelhi.imd.gov.in"
    rsmc_bulletin_refresh_hours: int = 3

    # ── MOSDAC / ISRO ─────────────────────────────────────────────────────────
    # Requires registered account. Privileged access for NRT data.
    # Contact: https://www.mosdac.gov.in
    mosdac_username: str = ""
    mosdac_password: str = ""
    mosdac_api_url: str = "https://www.mosdac.gov.in"
    mosdac_enabled: bool = False
    # Discovery is public; downloads remain separately disabled until a
    # persistent storage location and an administrator token are configured.
    mosdac_download_enabled: bool = False
    satellite_admin_token: str = ""
    mosdac_request_timeout_seconds: int = 60
    mosdac_discovery_refresh_minutes: int = 60
    # Keep legacy key name for backward compat
    mosdac_api_key: str = ""

    # ── Data Freshness Thresholds ─────────────────────────────────────────────
    # An observation is LIVE if received within this many hours
    data_live_threshold_hours: int = 6
    # An observation is DELAYED if within this many hours (else STALE)
    data_delayed_threshold_hours: int = 24

    # ── Satellite Imagery (Phase 3) ─────────────────────────────────────────
    satellite_enabled: bool = True
    gibs_wmts_url: str = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"
    gibs_tile_cache_seconds: int = 3600   # 1h browser cache for proxied tiles
    # Persistent storage for downloaded source products. Keep raw products out
    # of the database; a Render disk or object storage mount is required in production.
    satellite_storage_dir: str = "data/satellite"
    satellite_max_download_mb: int = 2048

    # ── AI ────────────────────────────────────────────────────────────────────
    ai_model_dir: str = "../models"
    ai_device: str = "auto"   # auto | cuda | cpu
    ai_max_image_mb: int = 10


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
