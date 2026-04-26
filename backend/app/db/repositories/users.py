"""User persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


@dataclass(frozen=True)
class UserRow:
    clerk_user_id: str
    email: str | None
    created_at: datetime
    last_seen_at: datetime


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_clerk_user(
        self, clerk_user_id: str, email: str | None
    ) -> UserRow:
        """Insert or update a row keyed by Clerk `sub` (upsert, single round trip)."""
        ins = insert(User).values(
            clerk_user_id=clerk_user_id,
            email=email,
            last_seen_at=func.now(),
        )
        ex = ins.excluded
        stmt = ins.on_conflict_do_update(
            index_elements=[User.clerk_user_id],
            set_={
                "email": func.coalesce(ex.email, User.email),
                "last_seen_at": func.now(),
            },
        ).returning(User)
        result = await self._session.execute(stmt)
        u = result.scalars().one()
        return UserRow(
            clerk_user_id=u.clerk_user_id,
            email=u.email,
            created_at=u.created_at,
            last_seen_at=u.last_seen_at,
        )
