"""Plan catalog single-source tests."""

from __future__ import annotations

import pytest

from app.billing.plan_catalog import SUBSCRIPTION_PRODUCTS, reconcile_plan_catalog


class _FakePlanRepo:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def update_catalog_pricing(self, **kwargs) -> int:
        self.calls.append(kwargs)
        return 1


@pytest.mark.asyncio
async def test_reconcile_plan_catalog_applies_all_specs() -> None:
    repo = _FakePlanRepo()

    updated = await reconcile_plan_catalog(repo)

    assert updated == len(SUBSCRIPTION_PRODUCTS) == 4
    assert {c["slug"] for c in repo.calls} == {
        "plus_monthly",
        "plus_yearly",
        "pro_monthly",
        "pro_yearly",
    }
    for call in repo.calls:
        assert call["price_cents"] > 0
        assert call["billing_period"] in ("monthly", "yearly")
