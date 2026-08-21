"""Plan catalog persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Plan

UNLIMITED = -1


@dataclass(frozen=True)
class PlanRow:
    id: int
    slug: str
    name: str
    billing_period: str | None
    dodo_product_id: str | None
    price_cents: int | None
    words_per_day: int
    uploads_per_day: int
    upload_bytes_per_day: int
    max_upload_bytes_per_import: int
    files_in_scope: int
    is_active: bool
    created_at: datetime


def _to_row(p: Plan) -> PlanRow:
    return PlanRow(
        id=p.id,
        slug=p.slug,
        name=p.name,
        billing_period=p.billing_period,
        dodo_product_id=p.dodo_product_id,
        price_cents=p.price_cents,
        words_per_day=p.words_per_day,
        uploads_per_day=p.uploads_per_day,
        upload_bytes_per_day=p.upload_bytes_per_day,
        max_upload_bytes_per_import=p.max_upload_bytes_per_import,
        files_in_scope=p.files_in_scope,
        is_active=p.is_active,
        created_at=p.created_at,
    )


class PlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_slug(self, slug: str) -> PlanRow | None:
        result = await self._session.execute(
            select(Plan).where(Plan.slug == slug).limit(1)
        )
        plan = result.scalars().first()
        return _to_row(plan) if plan else None

    async def get_by_dodo_product_id(self, dodo_product_id: str) -> PlanRow | None:
        result = await self._session.execute(
            select(Plan).where(Plan.dodo_product_id == dodo_product_id).limit(1)
        )
        plan = result.scalars().first()
        return _to_row(plan) if plan else None

    async def list_active(self) -> list[PlanRow]:
        result = await self._session.execute(
            select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.id)
        )
        return [_to_row(p) for p in result.scalars().all()]

    async def get_free_plan(self) -> PlanRow | None:
        return await self.get_by_slug("free")

    async def set_dodo_product_id_by_slug(
        self, slug: str, dodo_product_id: str
    ) -> None:
        await self._session.execute(
            update(Plan)
            .where(Plan.slug == slug)
            .values(dodo_product_id=dodo_product_id)
        )

    async def update_catalog_pricing(
        self,
        *,
        slug: str,
        name: str,
        billing_period: str,
        price_cents: int,
    ) -> int:
        """Re-apply catalog pricing to a plan row; returns rows updated."""
        result = await self._session.execute(
            update(Plan)
            .where(Plan.slug == slug)
            .values(
                name=name,
                billing_period=billing_period,
                price_cents=price_cents,
            )
        )
        return result.rowcount or 0
