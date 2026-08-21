"""Daily usage rollup persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UsageMeter


@dataclass(frozen=True)
class UsageMeterRow:
    id: int
    user_id: str
    usage_date: date
    ai_words: int
    uploads: int
    upload_bytes: int
    updated_at: datetime


def _to_row(m: UsageMeter) -> UsageMeterRow:
    return UsageMeterRow(
        id=m.id,
        user_id=m.user_id,
        usage_date=m.usage_date,
        ai_words=m.ai_words,
        uploads=m.uploads,
        upload_bytes=m.upload_bytes,
        updated_at=m.updated_at,
    )


class UsageMeterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_user_date(
        self, user_id: str, usage_date: date
    ) -> UsageMeterRow | None:
        result = await self._session.execute(
            select(UsageMeter).where(
                UsageMeter.user_id == user_id,
                UsageMeter.usage_date == usage_date,
            )
        )
        meter = result.scalars().first()
        return _to_row(meter) if meter else None

    async def increment(
        self,
        user_id: str,
        usage_date: date,
        *,
        ai_words: int = 0,
        uploads: int = 0,
        upload_bytes: int = 0,
    ) -> UsageMeterRow:
        """Atomically add to today's counters (upsert on user_id + usage_date)."""
        stmt = insert(UsageMeter).values(
            user_id=user_id,
            usage_date=usage_date,
            ai_words=ai_words,
            uploads=uploads,
            upload_bytes=upload_bytes,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[UsageMeter.user_id, UsageMeter.usage_date],
            set_={
                "ai_words": UsageMeter.ai_words + ai_words,
                "uploads": UsageMeter.uploads + uploads,
                "upload_bytes": UsageMeter.upload_bytes + upload_bytes,
                "updated_at": func.now(),
            },
        ).returning(UsageMeter)
        result = await self._session.execute(stmt)
        meter = result.scalars().one()
        return _to_row(meter)
