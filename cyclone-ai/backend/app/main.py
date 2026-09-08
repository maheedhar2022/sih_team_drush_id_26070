"""
CycloneAI — FastAPI Application Entry Point

Initializes:
- CORS middleware (configured from environment)
- API routers (health + cyclones)
- Startup/shutdown lifecycle logging
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("cyclone_ai")


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info("=" * 60)
    logger.info("CycloneAI Backend starting up")
    logger.info(f"  Version    : {settings.app_version}")
    logger.info(f"  Environment: {settings.app_env}")
    logger.info(f"  Demo Mode  : {settings.demo_mode}")
    logger.info(f"  CORS       : {settings.cors_origins}")
    logger.info("=" * 60)
    yield
    logger.info("CycloneAI Backend shutting down.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
settings = get_settings()

app = FastAPI(
    title="CycloneAI API",
    description=(
        "Real-Time AI-Based Tropical Cyclone Monitoring, Analysis, "
        "Classification and Prediction Platform — API"
    ),
    version=settings.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(api_router)


# ---------------------------------------------------------------------------
# Root redirect info
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {
        "service": "CycloneAI API",
        "version": settings.app_version,
        "docs": "/api/docs",
        "health": "/api/health",
    }
