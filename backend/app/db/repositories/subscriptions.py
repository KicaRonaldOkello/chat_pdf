"""Paid subscription persistence. Dodo webhooks are the source of truth."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Plan, Subscription


@dataclass(frozen=True)
class SubscriptionRow:
    id: int
    user_id: str
    plan_id: int
    plan_slug: str
    dodo_subscription_id: str | None
    dodo_customer_id: str | None
    status: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    payment_method_id: str | None
    cancel_at_period_end: bool
    last_webhook_event: str | None
    last_webhook_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _to_row(sub: Subscription, plan_slug: str) -> SubscriptionRow:
    return SubscriptionRow(
        id=sub.id,
        user_id=sub.user_id,
        plan_id=sub.plan_id,
        plan_slug=plan_slug,
        dodo_subscription_id=sub.dodo_subscription_id,
        dodo_customer_id=sub.dodo_customer_id,
        status=sub.status,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        payment_method_id=sub.payment_method_id,
        cancel_at_period_end=sub.cancel_at_period_end,
        last_webhook_event=sub.last_webhook_event,
        last_webhook_at=sub.last_webhook_at,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_user(self, user_id: str) -> SubscriptionRow | None:
        stmt = (
            select(Subscription, Plan.slug)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        return _to_row(row[0], row[1]) if row else None

    async def get_by_dodo_subscription_id(
        self, dodo_subscription_id: str
    ) -> SubscriptionRow | None:
        stmt = (
            select(Subscription, Plan.slug)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.dodo_subscription_id == dodo_subscription_id)
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.first()
        return _to_row(row[0], row[1]) if row else None

    async def upsert_from_dodo(
        self,
        *,
        user_id: str,
        plan_id: int,
        dodo_subscription_id: str | None,
        dodo_customer_id: str | None,
        status: str,
        current_period_start: datetime | None,
        current_period_end: datetime | None,
        payment_method_id: str | None,
        cancel_at_period_end: bool,
        last_webhook_event: str | None,
        last_webhook_at: datetime | None,
    ) -> SubscriptionRow:
        """Insert or update a subscription keyed by `dodo_subscription_id`."""
        stmt = insert(Subscription).values(
            user_id=user_id,
            plan_id=plan_id,
            dodo_subscription_id=dodo_subscription_id,
            dodo_customer_id=dodo_customer_id,
            status=status,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            payment_method_id=payment_method_id,
            cancel_at_period_end=cancel_at_period_end,
            last_webhook_event=last_webhook_event,
            last_webhook_at=last_webhook_at,
        )
        if dodo_subscription_id is not None:
            stmt = stmt.on_conflict_do_update(
                index_elements=[Subscription.dodo_subscription_id],
                set_={
                    "user_id": user_id,
                    "plan_id": plan_id,
                    "dodo_customer_id": dodo_customer_id,
                    "status": status,
                    "current_period_start": current_period_start,
                    "current_period_end": current_period_end,
                    "payment_method_id": payment_method_id,
                    "cancel_at_period_end": cancel_at_period_end,
                    "last_webhook_event": last_webhook_event,
                    "last_webhook_at": last_webhook_at,
                    "updated_at": func.now(),
                },
            )
        stmt = stmt.returning(Subscription.id)
        result = await self._session.execute(stmt)
        row_id = result.scalar_one()
        return await self._get_by_id(row_id)

    async def _get_by_id(self, row_id: int) -> SubscriptionRow:
        stmt = (
            select(Subscription, Plan.slug)
            .join(Plan, Plan.id == Subscription.plan_id)
            .where(Subscription.id == row_id)
        )
        result = await self._session.execute(stmt)
        row = result.one()
        return _to_row(row[0], row[1])
