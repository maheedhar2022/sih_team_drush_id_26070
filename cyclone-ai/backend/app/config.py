"""
CycloneAI Backend — Application Configuration
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

    # General
    app_env: str = "development"
    demo_mode: bool = True
    app_version: str = "0.1.0-phase1"

    # CORS — accepts a comma-separated string or a JSON list
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # Database
    database_url: str = "sqlite:///./cyclone_ai.db"

    # Cache (optional)
    redis_url: str = ""

    # Data sources
    mosdac_api_key: str = ""
    ibtracs_base_url: str = (
        "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/csv/"
    )

    # AI
    ai_model_dir: str = "../models"
    ai_device: str = "auto"  # auto | cuda | cpu


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
