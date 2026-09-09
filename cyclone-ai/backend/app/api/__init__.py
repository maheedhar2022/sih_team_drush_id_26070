"""CycloneAI — API package"""
from fastapi import APIRouter

from .ai import router as ai_router
from .analytics import router as analytics_router
from .cyclones import router as cyclones_router
from .data_sources import router as data_sources_router
from .health import router as health_router
from .realtime import router as realtime_router
from .satellite import router as satellite_router

api_router = APIRouter()
api_router.include_router(ai_router)
api_router.include_router(analytics_router)
api_router.include_router(health_router)
# The live route must be registered before the generic
# /api/cyclones/{cyclone_id} endpoint, otherwise "live" is parsed as an ID.
api_router.include_router(realtime_router)
api_router.include_router(cyclones_router)
api_router.include_router(data_sources_router)
api_router.include_router(satellite_router)

__all__ = ["api_router"]
