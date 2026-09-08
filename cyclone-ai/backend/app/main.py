"""
CycloneAI — FastAPI Application Entry Point (Phase 2)

Startup sequence:
  1. CORS middleware
  2. API routers (health + cyclones)
  3. DB init (create tables if not exist)
  4. Initial data ingest (if DB empty or stale)
  5. Background scheduler start
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("cyclone_ai")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("=" * 60)
    logger.info("CycloneAI Backend starting — Phase 2")
    logger.info("  Version    : %s", settings.app_version)
    logger.info("  Environment: %s", settings.app_env)
    logger.info("  Database   : %s", settings.database_url.split("///")[0])
    logger.info("  IBTrACS    : %s", settings.ibtracs_base_url[:60])
    logger.info("  RSMC Bulletin: %s", "enabled" if settings.rsmc_bulletin_enabled else "disabled")
    logger.info("  Satellite    : %s", "enabled (NASA GIBS)" if settings.satellite_enabled else "disabled")
    logger.info("=" * 60)

    # 1. Initialise DB (create tables)
    from app.db.session import init_db
    await init_db()

    # 2. Startup ingest (fetch from providers if DB is empty/stale)
    from app.services.scheduler import startup_ingest, start_scheduler
    await startup_ingest()

    # 3. Start background refresh scheduler
    start_scheduler()

    yield

    # Shutdown
    from app.services.scheduler import stop_scheduler
    stop_scheduler()
    logger.info("CycloneAI Backend shutting down.")


settings = get_settings()

app = FastAPI(
    title="CycloneAI API",
    description=(
        "Real-Time AI-Based Tropical Cyclone Monitoring, Analysis, "
        "Classification and Prediction Platform — Phase 2 API\n\n"
        "Data sources: IBTrACS v04r01 (NOAA NCEI), IMD/RSMC New Delhi"
    ),
    version=settings.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": "CycloneAI API",
        "version": settings.app_version,
        "phase": "2 — Data Ingestion",
        "docs": "/api/docs",
        "health": "/api/health",
        "sources": "/api/cyclones/sources/list",
    }
