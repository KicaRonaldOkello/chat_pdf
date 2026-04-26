"""Async SQLAlchemy engine (psycopg3 async DSN)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import DATABASE_URL


def to_async_dsn(dsn: str) -> str:
    """`postgresql://` -> `postgresql+psycopg_async://` for `create_async_engine`."""
    d = dsn.strip()
    if d.startswith("postgresql+psycopg_async://"):
        return d
    if d.startswith("postgresql+psycopg://"):
        return d.replace("postgresql+psycopg://", "postgresql+psycopg_async://", 1)
    if d.startswith("postgresql://"):
        return d.replace("postgresql://", "postgresql+psycopg_async://", 1)
    return d


async def open_db_engine() -> (
    tuple[AsyncEngine, async_sessionmaker[AsyncSession]] | None
):
    if not DATABASE_URL:
        return None
    engine = create_async_engine(
        to_async_dsn(DATABASE_URL), pool_size=5, max_overflow=0
    )
    sm = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return (engine, sm)


async def close_db_engine(engine: AsyncEngine | None) -> None:
    if engine is not None:
        await engine.dispose()
