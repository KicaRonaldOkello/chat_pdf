"""User persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


@dataclass(frozen=True)
class UserRow:
    user_id: str
    email: str | None
    name: str | None
    picture: str | None
    created_at: datetime
    last_seen_at: datetime


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_user(
        self,
        user_id: str,
        email: str | None,
        name: str | None = None,
        picture: str | None = None,
    ) -> UserRow:
        """Insert or update a row keyed by `user_id` (upsert, single round trip)."""
        ins = insert(User).values(
            user_id=user_id,
            email=email,
            name=name,
            picture=picture,
            last_seen_at=func.now(),
        )
        ex = ins.excluded
        stmt = ins.on_conflict_do_update(
            index_elements=[User.user_id],
            set_={
                "email": func.coalesce(ex.email, User.email),
                "name": func.coalesce(ex.name, User.name),
                "picture": func.coalesce(ex.picture, User.picture),
                "last_seen_at": func.now(),
            },
        ).returning(User)
        result = await self._session.execute(stmt)
        u = result.scalars().one()
        return UserRow(
            user_id=u.user_id,
            email=u.email,
            name=u.name,
            picture=u.picture,
            created_at=u.created_at,
            last_seen_at=u.last_seen_at,
        )

    async def get_by_email(self, email: str) -> UserRow | None:
        result = await self._session.execute(
            select(User).where(User.email == email).limit(1)
        )
        u = result.scalars().first()
        if u is None:
            return None
        return UserRow(
            user_id=u.user_id,
            email=u.email,
            name=u.name,
            picture=u.picture,
            created_at=u.created_at,
            last_seen_at=u.last_seen_at,
        )
