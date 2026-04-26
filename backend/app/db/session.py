"""Request-scoped async `AsyncSession` (FastAPI dependency)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request: commit on success, rollback on error."""
    sm: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "async_session_maker", None
    )
    if sm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured (set DATABASE_URL and run Alembic migrations).",
        )
    session = sm()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
