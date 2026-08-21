"""Dodo Payments client helpers (merchant of record).

The Dodo API key lives only in the backend — the Angular app never sees it.
The checkout flow redirects the user to Dodo's hosted checkout page.
"""

from __future__ import annotations

import logging
from typing import Any

from dodopayments import DodoPayments

from app.settings import settings

log = logging.getLogger(__name__)

from app.billing.plan_catalog import SUBSCRIPTION_PRODUCTS


def _client() -> DodoPayments:
    if not settings.dodo_api_key:
        raise RuntimeError(
            "DODO_API_KEY is not set — configure it in backend/.env before using billing."
        )
    return DodoPayments(
        bearer_token=settings.dodo_api_key,
        environment=settings.dodo_mode,  # type: ignore[arg-type]
    )


def unwrap_webhook(payload: str, headers: dict[str, str]) -> Any:
    """Verify a Dodo webhook signature and parse the event."""
    if not settings.dodo_webhook_secret:
        raise RuntimeError(
            "DODO_WEBHOOK_SECRET is not set — configure it in backend/.env before receiving webhooks."
        )
    # Signature verification is local; a bearer token is only required to satisfy
    # the client constructor (unused for unwrap).
    client = DodoPayments(
        bearer_token=settings.dodo_api_key or "unused",
        webhook_key=settings.dodo_webhook_secret,
    )
    return client.webhooks.unwrap(payload, headers=headers)


def _recurring_price(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "recurring_price",
        "currency": settings.dodo_billing_currency,
        "price": spec["price_cents"],
        "discount": 0,
        "purchasing_power_parity": False,
        "payment_frequency_count": spec["count"],
        "payment_frequency_interval": spec["interval"],
        "subscription_period_count": spec["count"],
        "subscription_period_interval": spec["interval"],
        "trial_period_days": settings.dodo_trial_days,
    }


def sync_subscription_products() -> dict[str, str]:
    """Ensure the four subscription products exist in Dodo (test or live mode).

    Matches existing products by ``metadata.plan_slug`` so reruns are idempotent.
    Returns a mapping of ``plan_slug -> dodo product_id``.
    """
    client = _client()
    existing: dict[str, str] = {}
    for product in client.products.list(recurring=True):
        meta = dict(product.metadata or {})
        slug = meta.get("plan_slug")
        if isinstance(slug, str) and slug:
            existing[slug] = product.product_id

    created: list[str] = []
    for spec in SUBSCRIPTION_PRODUCTS:
        if spec["slug"] in existing:
            continue
        product = client.products.create(
            name=spec["name"],
            price=_recurring_price(spec),
            tax_category="saas",
            metadata={"plan_slug": spec["slug"]},
        )
        existing[spec["slug"]] = product.product_id
        created.append(spec["slug"])

    if created:
        log.info("Created Dodo subscription products: %s", ", ".join(created))
    return existing


def create_checkout_session(payload: dict[str, Any]) -> str:
    """Create a Dodo checkout session and return the hosted checkout URL."""
    client = _client()
    response = client.checkout_sessions.create(**payload)
    if not response.checkout_url:
        raise RuntimeError("Dodo checkout session returned no checkout_url")
    return response.checkout_url
