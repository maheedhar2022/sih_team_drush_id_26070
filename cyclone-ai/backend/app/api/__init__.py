"""CycloneAI — API package"""
from fastapi import APIRouter

from .cyclones import router as cyclones_router
from .data_sources import router as data_sources_router
from .health import router as health_router
from .satellite import router as satellite_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(cyclones_router)
api_router.include_router(data_sources_router)
api_router.include_router(satellite_router)

__all__ = ["api_router"]
