"""Regression tests for the checkout endpoint (body parsing through slowapi)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.billing import router as billing_router
from app.auth.google_auth import require_session_token
from app.db.dependencies import (
    get_plan_repository,
    get_subscription_repository,
    get_usage_meter_repository,
)
from app.db.repositories import PlanRow, SubscriptionRow


def _plan() -> PlanRow:
    return PlanRow(
        id=2,
        slug="plus_monthly",
        name="Plus",
        billing_period="monthly",
        dodo_product_id="pdt_plus_monthly",
        price_cents=1200,
        words_per_day=10_000,
        uploads_per_day=10,
        upload_bytes_per_day=-1,
        max_upload_bytes_per_import=100 * 1024 * 1024,
        files_in_scope=10,
        is_active=True,
        created_at=datetime.now(UTC),
    )


def _free_plan() -> PlanRow:
    return PlanRow(
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


class _FakePlanRepo:
    async def get_by_slug(self, slug: str) -> PlanRow | None:
        return _plan() if slug == "plus_monthly" else None


class _StatusPlanRepo:
    async def get_by_slug(self, slug: str) -> PlanRow | None:
        if slug == "pro_monthly":
            return replace(_plan(), slug="pro_monthly")
        if slug == "free":
            return _free_plan()
        return None

    async def get_free_plan(self) -> PlanRow | None:
        return _free_plan()


class _StatusSubscriptionRepo:
    def __init__(self, row: SubscriptionRow | None):
        self.row = row

    async def get_for_user(self, user_id: str) -> SubscriptionRow | None:
        return self.row


class _StatusUsageRepo:
    async def get_for_user_date(self, user_id: str, usage_date) -> None:
        return None


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(billing_router)
    app.dependency_overrides[require_session_token] = lambda: {
        "sub": "user-1",
        "email": "user@example.com",
        "name": "User",
    }
    app.dependency_overrides[get_plan_repository] = lambda: _FakePlanRepo()
    return app


def _make_status_app(subscription: SubscriptionRow | None) -> FastAPI:
    app = FastAPI()
    app.include_router(billing_router)
    app.dependency_overrides[require_session_token] = lambda: {
        "sub": "user-1",
        "email": "user@example.com",
    }
    app.dependency_overrides[get_plan_repository] = lambda: _StatusPlanRepo()
    app.dependency_overrides[get_subscription_repository] = (
        lambda: _StatusSubscriptionRepo(subscription)
    )
    app.dependency_overrides[get_usage_meter_repository] = lambda: _StatusUsageRepo()
    return app


def _subscription_row(status: str) -> SubscriptionRow:
    return SubscriptionRow(
        id=1,
        user_id="user-1",
        plan_id=3,
        plan_slug="pro_monthly",
        dodo_subscription_id="sub_1",
        dodo_customer_id="cus_1",
        status=status,
        current_period_start=datetime.now(UTC),
        current_period_end=datetime.now(UTC),
        payment_method_id=None,
        cancel_at_period_end=False,
        last_webhook_event="subscription.updated",
        last_webhook_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def test_status_reports_free_when_subscription_failed() -> None:
    app = _make_status_app(_subscription_row("failed"))
    with TestClient(app) as client:
        response = client.get("/api/billing/status")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan"]["slug"] == "free"
    assert body["subscription"]["status"] == "failed"


def test_status_reports_paid_plan_when_subscription_active() -> None:
    app = _make_status_app(_subscription_row("active"))
    with TestClient(app) as client:
        response = client.get("/api/billing/status")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["plan"]["slug"] == "pro_monthly"
    assert body["subscription"]["status"] == "active"


def test_checkout_parses_json_body_and_returns_url() -> None:
    app = _make_app()
    with (
        patch(
            "app.api.routes.billing.dodo.create_checkout_session",
            return_value="https://test.checkout.dodopayments.com/session/cks_test",
        ),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/billing/checkout",
            json={"tier": "plus", "period": "monthly"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["checkout_url"].startswith(
        "https://test.checkout.dodopayments.com"
    )


def test_checkout_rejects_invalid_tier() -> None:
    app = _make_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/billing/checkout",
            json={"tier": "enterprise", "period": "monthly"},
        )
    assert response.status_code == 422
