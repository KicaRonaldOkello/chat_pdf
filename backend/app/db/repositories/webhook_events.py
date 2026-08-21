"""Idempotency ledger for Dodo webhook deliveries."""

from __future__ import annotations

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DodoWebhookEvent


class WebhookEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, event_id: str, event_type: str, payload: dict | None) -> bool:
        """Insert the event as 'processing'; False if already processed/replayed."""
        stmt = insert(DodoWebhookEvent).values(
            event_id=event_id,
            event_type=event_type,
            status="processing",
            payload=payload,
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=[DodoWebhookEvent.event_id])
        stmt = stmt.returning(DodoWebhookEvent.event_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def mark_done(self, event_id: str) -> None:
        await self._session.execute(
            update(DodoWebhookEvent)
            .where(DodoWebhookEvent.event_id == event_id)
            .values(status="done", processed_at=func.now())
        )
