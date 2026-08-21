"""Single source of truth for the paid plan catalog (prices + Dodo billing).

``SUBSCRIPTION_PRODUCTS`` drives both the Dodo product sync and local plan
pricing, so prices can only drift if the database was seeded before this
module existed.  ``reconcile_plan_catalog`` re-applies the catalog to the
``plans`` table at startup to close that gap.
"""

from __future__ import annotations

from typing import Any

from app.db.repositories import PlanRepository

SUBSCRIPTION_PRODUCTS: tuple[dict[str, Any], ...] = (
    {
        "slug": "plus_monthly",
        "name": "Understanding Notes Plus (Monthly)",
        "price_cents": 1_200,
        "interval": "Month",
        "count": 1,
    },
    {
        "slug": "plus_yearly",
        "name": "Understanding Notes Plus (Yearly)",
        "price_cents": 11_520,
        "interval": "Year",
        "count": 1,
    },
    {
        "slug": "pro_monthly",
        "name": "Understanding Notes Pro (Monthly)",
        "price_cents": 2_400,
        "interval": "Month",
        "count": 1,
    },
    {
        "slug": "pro_yearly",
        "name": "Understanding Notes Pro (Yearly)",
        "price_cents": 23_040,
        "interval": "Year",
        "count": 1,
    },
)


async def reconcile_plan_catalog(plan_repo: PlanRepository) -> int:
    """Update local plan rows from the catalog; returns rows changed."""
    updated = 0
    for spec in SUBSCRIPTION_PRODUCTS:
        changed = await plan_repo.update_catalog_pricing(
            slug=spec["slug"],
            name=spec["name"],
            billing_period="monthly" if spec["count"] == 1 else "yearly",
            price_cents=spec["price_cents"],
        )
        updated += changed
    return updated
