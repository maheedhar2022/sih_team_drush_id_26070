"""CycloneAI — API package"""
from fastapi import APIRouter

from .cyclones import router as cyclones_router
from .health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(cyclones_router)

__all__ = ["api_router"]
