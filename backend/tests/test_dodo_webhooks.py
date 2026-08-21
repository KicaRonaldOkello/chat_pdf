"""Unit tests for Dodo webhook verification and subscription event mapping."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from standardwebhooks import Webhook

from app.billing import dodo, webhooks


def _subscription_dict(**overrides) -> dict:
    payload = {
        "business_id": "biz_1",
        "addons": [],
        "billing": {"country": "US"},
        "brand_id": "brand_1",
        "cancel_at_next_billing_date": False,
        "created_at": "2026-08-20T10:00:00Z",
        "credit_entitlement_cart": [],
        "currency": "USD",
        "customer": {
            "customer_id": "cus_1",
            "email": "user@example.com",
            "name": "Test User",
        },
        "metadata": {"user_id": "u1", "plan_slug": "plus_monthly"},
        "meter_credit_entitlement_cart": [],
        "meters": [],
        "next_billing_date": "2026-09-20T10:00:00Z",
        "on_demand": False,
        "payment_frequency_count": 1,
        "payment_frequency_interval": "Month",
        "previous_billing_date": "2026-08-20T10:00:00Z",
        "product_id": "pdt_plus_monthly",
        "quantity": 1,
        "recurring_pre_tax_amount": 1200,
        "status": "active",
        "subscription_id": "sub_1",
        "subscription_period_count": 1,
        "subscription_period_interval": "Month",
        "tax_inclusive": False,
        "trial_period_days": 0,
        "payment_method_id": "pm_1",
    }
    payload.update(overrides)
    return payload


def _signed_delivery(
    secret: str, event_type: str, data: dict, msg_id: str = "evt_1"
) -> tuple[str, dict[str, str]]:
    hook = Webhook(secret)
    timestamp = datetime.now(UTC)
    payload = json.dumps(
        {
            "type": event_type,
            "data": data,
            "timestamp": "2026-08-20T10:30:00Z",
            "business_id": "biz_1",
        }
    )
    signed = hook.sign(msg_id, timestamp, payload)
    headers = {
        "webhook-id": msg_id,
        "webhook-timestamp": str(int(timestamp.timestamp())),
        "webhook-signature": signed,
        "content-type": "application/json",
    }
    return payload, headers


def test_unwrap_verifies_signature(monkeypatch) -> None:
    secret = "whsec_test_secret"
    monkeypatch.setattr(dodo.settings, "dodo_webhook_secret", secret)
    payload, headers = _signed_delivery(
        secret, "subscription.active", _subscription_dict()
    )
    event = dodo.unwrap_webhook(payload, headers)
    assert event.type == "subscription.active"
    assert event.data.subscription_id == "sub_1"
    assert event.data.metadata["plan_slug"] == "plus_monthly"


def test_unwrap_rejects_bad_signature(monkeypatch) -> None:
    secret = "whsec_test_secret"
    monkeypatch.setattr(dodo.settings, "dodo_webhook_secret", secret)
    payload, headers = _signed_delivery(
        secret, "subscription.active", _subscription_dict()
    )
    headers["webhook-signature"] = "v1,deadbeef"
    try:
        dodo.unwrap_webhook(payload, headers)
    except Exception as exc:
        assert "verify" in type(exc).__name__.lower() or "signature" in str(exc).lower()
    else:
        raise AssertionError("expected signature verification to fail")


def test_payload_dict_is_json_serializable(monkeypatch) -> None:
    """Parsed SDK events contain datetimes; the ledger payload must survive json.dumps."""
    secret = "whsec_test_secret"
    monkeypatch.setattr(dodo.settings, "dodo_webhook_secret", secret)
    payload, headers = _signed_delivery(
        secret, "subscription.active", _subscription_dict()
    )
    event = dodo.unwrap_webhook(payload, headers)

    dumped = webhooks._payload_dict(event)
    assert isinstance(dumped, dict)
    json.dumps(dumped)  # must not raise TypeError
    assert isinstance(dumped["data"]["created_at"], str)
    assert "T" in dumped["data"]["created_at"]


def test_event_key_stable_and_distinct() -> None:
    ts = datetime(2026, 8, 20, 10, 30, tzinfo=UTC)
    sub_event = SimpleNamespace(
        type="subscription.active",
        timestamp=ts,
        data=SimpleNamespace(subscription_id="sub_1", payment_id=None),
    )
    payment_event = SimpleNamespace(
        type="payment.succeeded",
        timestamp=ts,
        data=SimpleNamespace(subscription_id=None, payment_id="pay_1"),
    )
    assert (
        webhooks.event_key(sub_event)
        == "subscription.active:sub_1:2026-08-20T10:30:00+00:00"
    )
    assert webhooks.event_key(payment_event) != webhooks.event_key(sub_event)


def test_event_key_prefers_provider_message_id() -> None:
    ts = datetime(2026, 8, 20, 10, 30, tzinfo=UTC)
    event = SimpleNamespace(
        type="subscription.active",
        timestamp=ts,
        data=SimpleNamespace(subscription_id="sub_1", payment_id=None),
    )
    assert webhooks.event_key(event, message_id="evt_abc") == "msg:evt_abc"


class _FakePlanRepo:
    def __init__(self, by_slug: dict | None = None, by_product: dict | None = None):
        self.by_slug = by_slug or {}
        self.by_product = by_product or {}

    async def get_by_slug(self, slug: str):
        return self.by_slug.get(slug)

    async def get_by_dodo_product_id(self, product_id: str):
        return self.by_product.get(product_id)


class _FakeSubscriptionRepo:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.existing = None

    async def upsert_from_dodo(self, **kwargs) -> None:
        self.calls.append(kwargs)

    async def get_by_dodo_subscription_id(self, sub_id: str):
        return self.existing


class _FakeUserRepo:
    def __init__(self, by_email: dict | None = None):
        self.by_email = by_email or {}

    async def get_by_email(self, email: str):
        return self.by_email.get(email)


def _sub_data(**overrides) -> SimpleNamespace:
    values = dict(
        subscription_id="sub_1",
        product_id="pdt_plus_monthly",
        metadata={"user_id": "u1", "plan_slug": "plus_monthly"},
        customer=SimpleNamespace(customer_id="cus_1", email="user@example.com"),
        status="active",
        previous_billing_date=datetime(2026, 8, 20, tzinfo=UTC),
        next_billing_date=datetime(2026, 9, 20, tzinfo=UTC),
        payment_method_id="pm_1",
        cancel_at_next_billing_date=False,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


async def test_subscription_event_upserts_with_mapped_fields() -> None:
    plan = SimpleNamespace(id=2, slug="plus_monthly")
    plan_repo = _FakePlanRepo(
        by_slug={"plus_monthly": plan},
        by_product={"pdt_plus_monthly": plan},
    )
    sub_repo = _FakeSubscriptionRepo()
    user_repo = _FakeUserRepo()

    await webhooks.process_subscription_event(
        event_type="subscription.active",
        data=_sub_data(),
        plan_repo=plan_repo,
        subscription_repo=sub_repo,
        user_repo=user_repo,
        timestamp=datetime(2026, 8, 20, 10, 30, tzinfo=UTC),
    )

    assert len(sub_repo.calls) == 1
    call = sub_repo.calls[0]
    assert call["user_id"] == "u1"
    assert call["plan_id"] == 2
    assert call["dodo_subscription_id"] == "sub_1"
    assert call["dodo_customer_id"] == "cus_1"
    assert call["status"] == "active"
    assert call["cancel_at_period_end"] is False
    assert call["last_webhook_event"] == "subscription.active"


async def test_subscription_event_falls_back_to_product_id() -> None:
    plan = SimpleNamespace(id=3, slug="pro_monthly")
    plan_repo = _FakePlanRepo(by_product={"pdt_pro_monthly": plan})
    sub_repo = _FakeSubscriptionRepo()
    user_repo = _FakeUserRepo()

    await webhooks.process_subscription_event(
        event_type="subscription.updated",
        data=_sub_data(
            metadata={"user_id": "u1"},
            product_id="pdt_pro_monthly",
            status="active",
        ),
        plan_repo=plan_repo,
        subscription_repo=sub_repo,
        user_repo=user_repo,
        timestamp=None,
    )

    assert sub_repo.calls[0]["plan_id"] == 3


async def test_subscription_event_looks_up_user_by_email() -> None:
    plan = SimpleNamespace(id=2, slug="plus_monthly")
    plan_repo = _FakePlanRepo(
        by_slug={"plus_monthly": plan},
        by_product={"pdt_plus_monthly": plan},
    )
    sub_repo = _FakeSubscriptionRepo()
    user_repo = _FakeUserRepo(
        by_email={"user@example.com": SimpleNamespace(user_id="u_google")}
    )

    await webhooks.process_subscription_event(
        event_type="subscription.active",
        data=_sub_data(metadata={}),
        plan_repo=plan_repo,
        subscription_repo=sub_repo,
        user_repo=user_repo,
        timestamp=None,
    )

    assert sub_repo.calls[0]["user_id"] == "u_google"


async def test_subscription_event_skips_without_user_or_plan() -> None:
    sub_repo = _FakeSubscriptionRepo()
    await webhooks.process_subscription_event(
        event_type="subscription.active",
        data=_sub_data(metadata={}, product_id="pdt_unknown"),
        plan_repo=_FakePlanRepo(),
        subscription_repo=sub_repo,
        user_repo=_FakeUserRepo(),
        timestamp=None,
    )
    assert sub_repo.calls == []


async def test_subscription_event_ignores_out_of_order_delivery() -> None:
    plan = SimpleNamespace(id=2, slug="plus_monthly")
    plan_repo = _FakePlanRepo(
        by_slug={"plus_monthly": plan},
        by_product={"pdt_plus_monthly": plan},
    )
    sub_repo = _FakeSubscriptionRepo()
    sub_repo.existing = SimpleNamespace(
        last_webhook_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        last_webhook_event="subscription.active",
    )

    await webhooks.process_subscription_event(
        event_type="subscription.cancelled",
        data=_sub_data(status="cancelled"),
        plan_repo=plan_repo,
        subscription_repo=sub_repo,
        user_repo=_FakeUserRepo(),
        timestamp=datetime(2026, 8, 21, 10, 0, tzinfo=UTC),
    )

    assert sub_repo.calls == []  # older event must not overwrite newer state


async def test_subscription_event_ignores_same_timestamp_delivery() -> None:
    """Equal timestamps cannot be ordered — treat them as replays and skip."""
    plan = SimpleNamespace(id=2, slug="plus_monthly")
    sub_repo = _FakeSubscriptionRepo()
    sub_repo.existing = SimpleNamespace(
        last_webhook_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        last_webhook_event="subscription.updated",
    )

    await webhooks.process_subscription_event(
        event_type="subscription.cancelled",
        data=_sub_data(status="cancelled"),
        plan_repo=_FakePlanRepo(by_slug={"plus_monthly": plan}),
        subscription_repo=sub_repo,
        user_repo=_FakeUserRepo(),
        timestamp=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )

    assert sub_repo.calls == []


async def test_subscription_event_preserves_period_when_dates_omitted() -> None:
    """A cancellation without next_billing_date must keep paid access until
    the end of the already-known billing period."""
    plan = SimpleNamespace(id=2, slug="plus_monthly")
    sub_repo = _FakeSubscriptionRepo()
    sub_repo.existing = SimpleNamespace(
        last_webhook_at=datetime(2026, 8, 21, tzinfo=UTC),
        current_period_start=datetime(2026, 8, 20, tzinfo=UTC),
        current_period_end=datetime(2026, 9, 20, tzinfo=UTC),
    )

    await webhooks.process_subscription_event(
        event_type="subscription.cancelled",
        data=_sub_data(
            status="cancelled",
            previous_billing_date=None,
            next_billing_date=None,
        ),
        plan_repo=_FakePlanRepo(by_slug={"plus_monthly": plan}),
        subscription_repo=sub_repo,
        user_repo=_FakeUserRepo(),
        timestamp=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )

    call = sub_repo.calls[0]
    assert call["status"] == "cancelled"
    assert call["current_period_start"] == datetime(2026, 8, 20, tzinfo=UTC)
    assert call["current_period_end"] == datetime(2026, 9, 20, tzinfo=UTC)


async def test_subscription_event_new_dates_take_precedence() -> None:
    """When the provider does send a billing window, it wins over stored values."""
    plan = SimpleNamespace(id=2, slug="plus_monthly")
    sub_repo = _FakeSubscriptionRepo()
    sub_repo.existing = SimpleNamespace(
        last_webhook_at=None,
        current_period_start=datetime(2026, 1, 1, tzinfo=UTC),
        current_period_end=datetime(2026, 2, 1, tzinfo=UTC),
    )

    await webhooks.process_subscription_event(
        event_type="subscription.active",
        data=_sub_data(),
        plan_repo=_FakePlanRepo(by_slug={"plus_monthly": plan}),
        subscription_repo=sub_repo,
        user_repo=_FakeUserRepo(),
        timestamp=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
    )

    call = sub_repo.calls[0]
    assert call["current_period_start"] == datetime(2026, 8, 20, tzinfo=UTC)
    assert call["current_period_end"] == datetime(2026, 9, 20, tzinfo=UTC)
