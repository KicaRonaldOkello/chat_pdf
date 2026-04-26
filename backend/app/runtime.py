"""Process-wide runtime handles set from FastAPI lifespan (e.g. async DB session factory)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Set by `app.main` when DATABASE_URL is configured
db_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_db_session_maker() -> async_sessionmaker[AsyncSession] | None:
    return db_session_maker
