"""
CycloneAI — Async SQLAlchemy Session Factory

Supports:
  SQLite (dev):     DATABASE_URL=sqlite+aiosqlite:///./cycloneai.db
  PostgreSQL (prod):DATABASE_URL=postgresql+asyncpg://user:pass@host/db
"""
from __future__ import annotations

import logging

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
    """Create all tables if they don't exist (schema-first for dev)."""
    # Import models so they register with Base metadata
    import app.db.models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialised.")


async def get_db():
    """FastAPI dependency — yields an async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
