"""Dodo webhook processing — subscriptions are the source of truth."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from app.db.repositories import (
    PlanRepository,
    SubscriptionRepository,
    UserRepository,
)
from app.db.repositories.webhook_events import WebhookEventRepository

log = logging.getLogger(__name__)


def event_key(event: Any, message_id: str | None = None) -> str:
    """Stable unique key for a delivery.

    Standard Webhooks ``webhook-id`` is the provider's own idempotency id
    (identical across retries of the same delivery), so prefer it.  Fall back
    to a synthetic key only when it is absent.
    """
    if message_id:
        return f"msg:{message_id}"
    data = getattr(event, "data", None)
    subject = (
        getattr(data, "subscription_id", None)
        or getattr(data, "payment_id", None)
        or "unknown"
    )
    timestamp = (
        getattr(event, "timestamp", None).isoformat()
        if getattr(event, "timestamp", None)
        else "0"
    )
    return f"{getattr(event, 'type', 'unknown')}:{subject}:{timestamp}"


async def process_event(
    event: Any, session_maker: Any, *, message_id: str | None = None
) -> None:
    """Process one verified webhook event with idempotency."""
    event_type = getattr(event, "type", "")
    key = event_key(event, message_id)
    async with session_maker() as session:
        repo = WebhookEventRepository(session)
        if not await repo.claim(key, event_type, _payload_dict(event)):
            log.info("duplicate dodo webhook %s; skipping", key)
            return
        try:
            data = getattr(event, "data", None)
            if event_type.startswith("subscription."):
                await process_subscription_event(
                    event_type=event_type,
                    data=data,
                    plan_repo=PlanRepository(session),
                    subscription_repo=SubscriptionRepository(session),
                    user_repo=UserRepository(session),
                    timestamp=getattr(event, "timestamp", None),
                )
            elif event_type.startswith("payment."):
                # Subscriptions drive entitlements; payments are bookkeeping.
                log.info(
                    "dodo payment event %s received (no entitlement change)", event_type
                )
            else:
                log.info("unhandled dodo event %s", event_type)
            await repo.mark_done(key)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def process_subscription_event(
    *,
    event_type: str,
    data: Any,
    plan_repo: PlanRepository,
    subscription_repo: SubscriptionRepository,
    user_repo: UserRepository,
    timestamp: datetime | None,
) -> None:
    """Map a Dodo subscription event to our subscriptions table."""
    if data is None:
        raise ValueError("subscription event missing data")

    sub_id = getattr(data, "subscription_id", None)
    product_id = getattr(data, "product_id", None)
    metadata = dict(getattr(data, "metadata", None) or {})

    user_id = metadata.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        email = getattr(getattr(data, "customer", None), "email", None)
        if email:
            user = await user_repo.get_by_email(email)
            user_id = user.user_id if user else None
    if not user_id:
        log.warning(
            "dodo subscription %s: no matching user (metadata user_id missing, email=%s)",
            sub_id,
            getattr(getattr(data, "customer", None), "email", None),
        )
        return

    plan_slug = metadata.get("plan_slug")
    plan = None
    if isinstance(plan_slug, str) and plan_slug:
        plan = await plan_repo.get_by_slug(plan_slug)
    if plan is None and product_id:
        plan = await plan_repo.get_by_dodo_product_id(product_id)
    if plan is None:
        log.warning(
            "dodo subscription %s: unknown product %s; skipping",
            sub_id,
            product_id,
        )
        return

    customer = getattr(data, "customer", None)

    # Last known subscription row, used both for the ordering guard below and
    # to survive provider payloads that omit the billing window.
    existing = None
    if sub_id:
        existing = await subscription_repo.get_by_dodo_subscription_id(sub_id)
        if (
            existing is not None
            and existing.last_webhook_at is not None
            and timestamp is not None
            and timestamp <= existing.last_webhook_at
        ):
            # Strictly-newer events only: equal timestamps are treated as
            # replays too (exact replays are already caught by the ledger,
            # so an equal-timestamp delivery is either a duplicate or two
            # events whose order cannot be established).
            log.info(
                "dodo subscription %s: ignoring stale or replayed %s "
                "(last %s at %s)",
                sub_id,
                event_type,
                existing.last_webhook_event,
                existing.last_webhook_at,
            )
            return

    # Preserve the last known billing period when the provider omits it —
    # cancellations often arrive without next_billing_date.  Overwriting the
    # stored period with NULLs would drop entitled access immediately even
    # though the paid period is still running ("access until the end of your
    # billing period").
    current_period_start = getattr(data, "previous_billing_date", None) or (
        getattr(existing, "current_period_start", None) if existing else None
    )
    current_period_end = getattr(data, "next_billing_date", None) or (
        getattr(existing, "current_period_end", None) if existing else None
    )

    await subscription_repo.upsert_from_dodo(
        user_id=user_id,
        plan_id=plan.id,
        dodo_subscription_id=sub_id,
        dodo_customer_id=getattr(customer, "customer_id", None),
        status=str(getattr(data, "status", "unknown")),
        current_period_start=current_period_start,
        current_period_end=current_period_end,
        payment_method_id=getattr(data, "payment_method_id", None),
        cancel_at_period_end=bool(getattr(data, "cancel_at_next_billing_date", False)),
        last_webhook_event=event_type,
        last_webhook_at=timestamp,
    )
    log.info(
        "dodo subscription %s -> plan %s (%s) for user %s",
        sub_id,
        plan.slug,
        event_type,
        user_id,
    )


def _json_safe(value: Any) -> Any:
    """Recursively convert non-JSON-serializable values into JSON-safe primitives."""
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return _json_safe(value.value)
    return value


def _payload_dict(event: Any) -> dict | None:
    """Flatten a parsed webhook event to a JSON-serializable dict for the ledger."""
    try:
        return event.model_dump(mode="json")
    except Exception:
        pass
    try:
        return _json_safe(event.model_dump())
    except Exception:
        return None
