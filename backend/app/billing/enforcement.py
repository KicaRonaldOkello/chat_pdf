"""Plan entitlement checks and usage metering for chat/upload endpoints."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text

from app.api.chat import chat_stream_ndjson, nd
from app.api.schemas import ChatRequest
from app.dates import utc_today
from app.db.repositories import (
    PlanRepository,
    PlanRow,
    SubscriptionRepository,
    SubscriptionRow,
    UsageMeterRepository,
    UsageMeterRow,
)

log = logging.getLogger(__name__)

_WORD_RE = re.compile(r"\S+")

# Subscriptions in these states keep their plan entitlements.
_KEEP_PLAN_STATUSES = {"active", "on_hold", "cancelled"}


def _subscription_entitles(subscription: SubscriptionRow) -> bool:
    """Defense-in-depth: non-active statuses keep entitlements only while the
    paid period is still running (in case Dodo's cancelled/expired webhook
    never arrives).

    Relies on ``app.billing.webhooks`` preserving the last known
    ``current_period_end`` when a provider payload omits it (e.g.
    cancellations), so the stored value stays meaningful here."""
    if subscription.status not in _KEEP_PLAN_STATUSES:
        return False
    if subscription.status == "active":
        return True
    return (
        subscription.current_period_end is not None
        and subscription.current_period_end >= datetime.now(UTC)
    )


_LIMIT_LABELS = {
    "words": "daily AI word limit",
    "uploads": "daily upload limit",
    "upload_bytes": "daily upload storage limit",
    "files_in_scope": "files-in-scope limit",
}


class UsageLimitExceeded(Exception):
    """Raised when a plan limit blocks an action; rendered as HTTP 402."""

    def __init__(
        self,
        *,
        limit_type: str,
        used: int,
        limit: int,
        upgrade: str | None,
        message: str | None = None,
    ) -> None:
        self.limit_type = limit_type
        self.used = used
        self.limit = limit
        self.upgrade = upgrade
        self.message = message or self._default_message()
        super().__init__(self.message)

    def _default_message(self) -> str:
        label = _LIMIT_LABELS.get(self.limit_type, "usage limit")
        if self.upgrade:
            return f"You've reached your {label}. Upgrade to {self.upgrade} for more."
        return f"You've reached your {label} ({self.used} of {self.limit})."


def upgrade_tier_for(plan_slug: str) -> str | None:
    """Next paid tier for a plan slug, or None if already at the top."""
    base = plan_slug.split("_", 1)[0]
    return {"free": "Plus", "plus": "Pro"}.get(base)


async def resolve_plan(
    plan_repo: PlanRepository,
    subscription_repo: SubscriptionRepository,
    user_id: str,
) -> PlanRow:
    """Current paid plan (when the subscription entitles it) or Free."""
    subscription = await subscription_repo.get_for_user(user_id)
    if subscription is not None and _subscription_entitles(subscription):
        plan = await plan_repo.get_by_slug(subscription.plan_slug)
        if plan is not None and plan.is_active:
            return plan
    free = await plan_repo.get_free_plan()
    if free is None:
        raise RuntimeError("Free plan is not configured")
    return free


def check_word_quota(plan: PlanRow, usage: UsageMeterRow | None) -> None:
    limit = plan.words_per_day
    if limit < 0:
        return
    used = usage.ai_words if usage else 0
    if used >= limit:
        raise UsageLimitExceeded(
            limit_type="words",
            used=used,
            limit=limit,
            upgrade=upgrade_tier_for(plan.slug),
        )


def check_upload_quota(
    plan: PlanRow,
    usage: UsageMeterRow | None,
    *,
    extra_bytes: int = 0,
) -> None:
    if plan.uploads_per_day >= 0:
        used = usage.uploads if usage else 0
        if used >= plan.uploads_per_day:
            raise UsageLimitExceeded(
                limit_type="uploads",
                used=used,
                limit=plan.uploads_per_day,
                upgrade=upgrade_tier_for(plan.slug),
            )
    if plan.upload_bytes_per_day >= 0:
        used_bytes = usage.upload_bytes if usage else 0
        if used_bytes + extra_bytes > plan.upload_bytes_per_day:
            raise UsageLimitExceeded(
                limit_type="upload_bytes",
                used=used_bytes,
                limit=plan.upload_bytes_per_day,
                upgrade=upgrade_tier_for(plan.slug),
            )


def check_files_in_scope(plan: PlanRow, count: int) -> None:
    if plan.files_in_scope >= 0 and count > plan.files_in_scope:
        raise UsageLimitExceeded(
            limit_type="files_in_scope",
            used=count,
            limit=plan.files_in_scope,
            upgrade=upgrade_tier_for(plan.slug),
        )


async def chat_stream_with_usage(
    body: ChatRequest,
    plan: PlanRow,
    usage: UsageMeterRow | None,
    usage_repo: UsageMeterRepository,
    user_id: str,
    *,
    session_maker: Any | None = None,
) -> AsyncIterator[bytes]:
    """Wrap the NDJSON chat stream, count AI words, cap at the daily quota.

    The current answer is allowed to finish (so citations aren't cut), but the
    meter is capped at the remaining allowance and a `limit_reached` event is
    emitted so the UI can prompt for an upgrade. Subsequent requests are
    blocked by the pre-check until the daily reset.

    The meter write runs in its own short-lived transaction (via ``session_maker``)
    rather than the request-scoped session, so a cancelled/disconnected stream
    can never leave the request's transaction open and lock the usage row.
    """
    limit = plan.words_per_day
    used = usage.ai_words if usage else 0
    remaining = None if limit < 0 else max(0, limit - used)
    counted = 0
    limit_notified = False
    limit_emitted = False
    prev_ended_midword = False
    try:
        async for chunk in chat_stream_ndjson(body):
            try:
                event = json.loads(chunk.decode("utf-8"))
            except Exception:
                event = None
            if event is not None and event.get("type") == "content":
                text = event.get("content") or ""
                words = len(_WORD_RE.findall(text))
                # A word split across chunk boundaries ("hel" + "lo") was
                # already counted as one token; don't count its continuation.
                if (
                    prev_ended_midword
                    and words
                    and not text[:1].isspace()
                ):
                    words -= 1
                prev_ended_midword = bool(text) and not text[-1].isspace()
                if words:
                    if remaining is not None and counted + words >= remaining:
                        if not limit_emitted:
                            counted = remaining
                            limit_notified = True
                    else:
                        if not limit_emitted:
                            counted += words
            yield chunk
            if limit_notified:
                yield nd(
                    {
                        "type": "limit_reached",
                        "limit_type": "words",
                        "used": limit,
                        "limit": limit,
                    }
                )
                limit_notified = False
                limit_emitted = True
        if counted:
            # Authoritative post-answer meter so the UI can update instantly
            # without a second request. The DB write below persists the same
            # numbers (used + counted), so the two can never drift.
            yield nd(
                {
                    "type": "usage",
                    "usage_date": utc_today().isoformat(),
                    "ai_words": used + counted,
                    "uploads": usage.uploads if usage else 0,
                    "upload_bytes": usage.upload_bytes if usage else 0,
                    "limit": limit,
                }
            )
    finally:
        if counted:
            try:
                await _record_word_usage(
                    usage_repo=usage_repo,
                    session_maker=session_maker,
                    user_id=user_id,
                    counted=counted,
                )
            except Exception:
                log.exception("failed to record AI word usage for user=%s", user_id)


async def _record_word_usage(
    *,
    usage_repo: UsageMeterRepository,
    session_maker: Any | None,
    user_id: str,
    counted: int,
) -> None:
    """Persist the word count in a dedicated, bounded transaction."""
    if session_maker is None:
        # Fallback used by callers/tests without a session factory.
        await usage_repo.increment(user_id, utc_today(), ai_words=counted)
        return
    async with session_maker() as session:
        # Don't let a contended lock (e.g. a stranded transaction from a
        # cancelled request) block the meter write indefinitely.
        await session.execute(text("SET LOCAL lock_timeout = '10s'"))
        await UsageMeterRepository(session).increment(
            user_id, utc_today(), ai_words=counted
        )
        await session.commit()
