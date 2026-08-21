"""Unit tests for plan-limit checks and the word-counting chat wrapper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.billing import enforcement
from app.dates import utc_today
from app.db.repositories import PlanRow, SubscriptionRow, UsageMeterRow


def _plan(**overrides) -> PlanRow:
    values = dict(
        id=1,
        slug="free",
        name="Free",
        billing_period=None,
        dodo_product_id=None,
        price_cents=0,
        words_per_day=2_000,
        uploads_per_day=5,
        upload_bytes_per_day=5 * 1024 * 1024,
        max_upload_bytes_per_import=5 * 1024 * 1024,
        files_in_scope=2,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    values.update(overrides)
    return PlanRow(**values)


def _usage(ai_words: int = 0, uploads: int = 0, upload_bytes: int = 0) -> UsageMeterRow:
    return UsageMeterRow(
        id=1,
        user_id="u1",
        usage_date=utc_today(),
        ai_words=ai_words,
        uploads=uploads,
        upload_bytes=upload_bytes,
        updated_at=datetime.now(UTC),
    )


def test_word_quota_blocks_at_limit() -> None:
    with pytest.raises(enforcement.UsageLimitExceeded) as exc_info:
        enforcement.check_word_quota(_plan(words_per_day=100), _usage(ai_words=100))
    assert exc_info.value.limit_type == "words"
    assert exc_info.value.upgrade == "Plus"


def test_word_quota_passes_below_limit() -> None:
    enforcement.check_word_quota(_plan(words_per_day=100), _usage(ai_words=99))


def test_word_quota_unlimited_never_blocks() -> None:
    enforcement.check_word_quota(_plan(words_per_day=-1), _usage(ai_words=10_000_000))


def test_upload_quota_blocks_uploads_and_bytes() -> None:
    with pytest.raises(enforcement.UsageLimitExceeded) as exc_info:
        enforcement.check_upload_quota(
            _plan(uploads_per_day=5), _usage(uploads=5, upload_bytes=100)
        )
    assert exc_info.value.limit_type == "uploads"

    with pytest.raises(enforcement.UsageLimitExceeded) as exc_info:
        enforcement.check_upload_quota(
            _plan(upload_bytes_per_day=1000),
            _usage(uploads=1, upload_bytes=900),
            extra_bytes=200,
        )
    assert exc_info.value.limit_type == "upload_bytes"


def test_files_in_scope_blocks() -> None:
    with pytest.raises(enforcement.UsageLimitExceeded) as exc_info:
        enforcement.check_files_in_scope(_plan(files_in_scope=2), 3)
    assert exc_info.value.limit_type == "files_in_scope"
    enforcement.check_files_in_scope(_plan(files_in_scope=2), 2)
    enforcement.check_files_in_scope(_plan(files_in_scope=-1), 99)


def test_upgrade_tier_mapping() -> None:
    assert enforcement.upgrade_tier_for("free") == "Plus"
    assert enforcement.upgrade_tier_for("plus_monthly") == "Pro"
    assert enforcement.upgrade_tier_for("pro_yearly") is None


class _FakeUsageRepo:
    def __init__(self) -> None:
        self.calls: list[tuple[str, date, dict]] = []

    async def increment(self, user_id: str, usage_date: date, **kwargs) -> None:
        self.calls.append((user_id, usage_date, kwargs))


class _FakeSession:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.committed = False

    async def execute(self, stmt) -> None:
        self.executed.append(str(stmt))

    async def commit(self) -> None:
        self.committed = True

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


class _FakeSessionMaker:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    def __call__(self) -> _FakeSession:
        return self.session


async def _fake_stream(*events: dict):
    from app.api.chat import nd

    for event in events:
        yield nd(event)


@pytest.mark.asyncio
async def test_chat_wrapper_caps_words_and_notifies(monkeypatch) -> None:
    content = "one two three four five six seven eight nine ten"
    events = (
        {"type": "stage", "name": "start"},
        {"type": "content", "content": content},
        {"type": "journey", "detail": "cited"},
    )
    monkeypatch.setattr(
        enforcement, "chat_stream_ndjson", lambda body: _fake_stream(*events)
    )
    repo = _FakeUsageRepo()

    plan = _plan(words_per_day=10)  # 10 words total
    usage = _usage(ai_words=6)  # 4 remaining
    events = [
        e.decode()
        for e in [
            chunk
            async for chunk in enforcement.chat_stream_with_usage(
                object(), plan, usage, repo, "u1"  # type: ignore[arg-type]
            )
        ]
    ]

    assert any('"type": "limit_reached"' in e for e in events)
    assert any('"type": "journey"' in e for e in events)
    assert repo.calls == [("u1", utc_today(), {"ai_words": 4})]
    usage_event = next(e for e in events if '"type": "usage"' in e)
    assert '"ai_words": 10' in usage_event
    assert '"limit": 10' in usage_event


@pytest.mark.asyncio
async def test_chat_wrapper_unlimited_counts_all(monkeypatch) -> None:
    events = ({"type": "content", "content": "one two three four five"},)
    monkeypatch.setattr(
        enforcement, "chat_stream_ndjson", lambda body: _fake_stream(*events)
    )
    repo = _FakeUsageRepo()

    plan = _plan(words_per_day=-1)
    events = [
        e.decode()
        for e in [
            chunk
            async for chunk in enforcement.chat_stream_with_usage(
                object(), plan, _usage(), repo, "u1"  # type: ignore[arg-type]
            )
        ]
    ]
    assert not any('"type": "limit_reached"' in e for e in events)
    assert repo.calls == [("u1", utc_today(), {"ai_words": 5})]
    usage_event = next(e for e in events if '"type": "usage"' in e)
    assert '"ai_words": 5' in usage_event
    assert '"limit": -1' in usage_event


@pytest.mark.asyncio
async def test_chat_wrapper_emits_limit_reached_once(monkeypatch) -> None:
    """Beyond the cap, only one limit_reached event fires per answer."""
    events = (
        {"type": "content", "content": "one two three four five"},
        {"type": "content", "content": "six seven eight nine ten"},
        {"type": "content", "content": "eleven twelve thirteen"},
    )
    monkeypatch.setattr(
        enforcement, "chat_stream_ndjson", lambda body: _fake_stream(*events)
    )
    repo = _FakeUsageRepo()

    decoded = [
        e.decode()
        for e in [
            chunk
            async for chunk in enforcement.chat_stream_with_usage(
                object(), _plan(words_per_day=10), _usage(ai_words=0), repo, "u1"
            )
        ]
    ]

    limit_events = [e for e in decoded if '"type": "limit_reached"' in e]
    assert len(limit_events) == 1
    assert repo.calls == [("u1", utc_today(), {"ai_words": 10})]


@pytest.mark.asyncio
async def test_chat_wrapper_counts_split_words_once(monkeypatch) -> None:
    """A word split across streamed chunks must count once ("hel"+"lo")."""
    events = (
        {"type": "content", "content": "hel"},
        {"type": "content", "content": "lo world"},
        {"type": "content", "content": " next"},
    )
    monkeypatch.setattr(
        enforcement, "chat_stream_ndjson", lambda body: _fake_stream(*events)
    )
    repo = _FakeUsageRepo()

    decoded = [
        e.decode()
        for e in [
            chunk
            async for chunk in enforcement.chat_stream_with_usage(
                object(), _plan(words_per_day=100), _usage(ai_words=0), repo, "u1"
            )
        ]
    ]

    usage_event = next(e for e in decoded if '"type": "usage"' in e)
    assert '"ai_words": 3' in usage_event  # hello, world, next
    assert repo.calls == [("u1", utc_today(), {"ai_words": 3})]


@pytest.mark.asyncio
async def test_chat_wrapper_records_in_own_transaction(monkeypatch) -> None:
    """The meter write must commit in its own session, never the request session."""
    events = ({"type": "content", "content": "one two three"},)
    monkeypatch.setattr(
        enforcement, "chat_stream_ndjson", lambda body: _fake_stream(*events)
    )
    request_repo = _FakeUsageRepo()
    own_repo = _FakeUsageRepo()
    session = _FakeSession()
    monkeypatch.setattr(enforcement, "UsageMeterRepository", lambda s: own_repo)

    chunks = [
        chunk
        async for chunk in enforcement.chat_stream_with_usage(
            object(),  # type: ignore[arg-type]
            _plan(words_per_day=100),
            _usage(ai_words=0),
            request_repo,
            "u1",
            session_maker=_FakeSessionMaker(session),
        )
    ]

    assert any(b'"type": "content"' in chunk for chunk in chunks)
    assert request_repo.calls == []  # request-scoped repo untouched
    assert own_repo.calls == [("u1", utc_today(), {"ai_words": 3})]
    assert session.committed is True
    assert any("lock_timeout" in item for item in session.executed)
    usage_event = next(
        chunk.decode() for chunk in chunks if b'"type": "usage"' in chunk
    )
    assert '"ai_words": 3' in usage_event


@pytest.mark.asyncio
async def test_chat_wrapper_within_quota_no_notice(monkeypatch) -> None:
    events = ({"type": "content", "content": "one two"},)
    monkeypatch.setattr(
        enforcement, "chat_stream_ndjson", lambda body: _fake_stream(*events)
    )
    repo = _FakeUsageRepo()

    plan = _plan(words_per_day=100)
    events = [
        e.decode()
        for e in [
            chunk
            async for chunk in enforcement.chat_stream_with_usage(
                object(), plan, _usage(ai_words=10), repo, "u1"  # type: ignore[arg-type]
            )
        ]
    ]
    assert not any('"type": "limit_reached"' in e for e in events)
    assert repo.calls == [("u1", utc_today(), {"ai_words": 2})]
    usage_event = next(e for e in events if '"type": "usage"' in e)
    assert '"ai_words": 12' in usage_event


class _FakePlanRepo:
    def __init__(self, plans: dict[str, PlanRow], free_slug: str = "free") -> None:
        self.plans = plans
        self.free_slug = free_slug

    async def get_by_slug(self, slug: str) -> PlanRow | None:
        return self.plans.get(slug)

    async def get_free_plan(self) -> PlanRow | None:
        return self.plans.get(self.free_slug)


class _FakeSubscriptionRepo:
    def __init__(self, row: SubscriptionRow | None) -> None:
        self.row = row

    async def get_for_user(self, user_id: str) -> SubscriptionRow | None:
        return self.row


def _sub_row(status: str, period_end: datetime) -> SubscriptionRow:
    now = datetime.now(UTC)
    return SubscriptionRow(
        id=1,
        user_id="u1",
        plan_id=2,
        plan_slug="plus_monthly",
        dodo_subscription_id="sub_1",
        dodo_customer_id="cus_1",
        status=status,
        current_period_start=now - timedelta(days=10),
        current_period_end=period_end,
        payment_method_id="pm_1",
        cancel_at_period_end=False,
        last_webhook_event="subscription.updated",
        last_webhook_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_resolve_plan_free_when_cancelled_period_expired() -> None:
    plans = {
        "free": _plan(),
        "plus_monthly": _plan(slug="plus_monthly", words_per_day=10_000),
    }
    sub = _sub_row("cancelled", datetime.now(UTC) - timedelta(days=1))

    plan = await enforcement.resolve_plan(
        _FakePlanRepo(plans), _FakeSubscriptionRepo(sub), "u1"
    )

    assert plan.slug == "free"


@pytest.mark.asyncio
async def test_resolve_plan_keeps_plan_when_cancelled_period_future() -> None:
    plans = {
        "free": _plan(),
        "plus_monthly": _plan(slug="plus_monthly", words_per_day=10_000),
    }
    sub = _sub_row("cancelled", datetime.now(UTC) + timedelta(days=5))

    plan = await enforcement.resolve_plan(
        _FakePlanRepo(plans), _FakeSubscriptionRepo(sub), "u1"
    )

    assert plan.slug == "plus_monthly"


@pytest.mark.asyncio
async def test_resolve_plan_free_when_on_hold_period_expired() -> None:
    plans = {
        "free": _plan(),
        "plus_monthly": _plan(slug="plus_monthly", words_per_day=10_000),
    }
    sub = _sub_row("on_hold", datetime.now(UTC) - timedelta(days=1))

    plan = await enforcement.resolve_plan(
        _FakePlanRepo(plans), _FakeSubscriptionRepo(sub), "u1"
    )

    assert plan.slug == "free"
