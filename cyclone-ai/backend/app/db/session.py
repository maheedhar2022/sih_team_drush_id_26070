"""
CycloneAI — Async SQLAlchemy Session Factory

Supports:
  SQLite (dev):     DATABASE_URL=sqlite+aiosqlite:///./cycloneai.db
  PostgreSQL (prod):DATABASE_URL=postgresql+asyncpg://user:pass@host/db
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = logging.getLogger("cyclone_ai.db")


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""
    pass


def _build_engine():
    settings = get_settings()
    url = settings.database_url

    # SQLite needs check_same_thread=False
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    return create_async_engine(
        url,
        echo=False,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create tables and apply narrowly scoped additive schema upgrades."""
    # Import models so they register with Base metadata
    import app.db.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_additive_schema_upgrades)
    logger.info("Database tables initialised.")


def _apply_additive_schema_upgrades(connection) -> None:
    """Keep schema-first deployments compatible with the Phase 3 catalog."""
    inspector = inspect(connection)
    if "satellite_observations" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("satellite_observations")}
    if "source_filename" not in columns:
        connection.execute(
            text("ALTER TABLE satellite_observations ADD COLUMN source_filename VARCHAR(512)")
        )
        logger.info("Applied additive satellite_observations.source_filename upgrade.")


async def get_db():
    """FastAPI dependency — yields an async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
