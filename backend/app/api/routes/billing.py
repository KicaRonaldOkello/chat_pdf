"""Routes under ``/api/billing`` — checkout and plan/usage status."""

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.auth.google_auth import require_session_token
from app.billing import dodo
from app.billing.enforcement import resolve_plan
from app.dates import utc_today
from app.db.dependencies import (
    get_plan_repository,
    get_subscription_repository,
    get_usage_meter_repository,
)
from app.db.repositories import (
    PlanRepository,
    PlanRow,
    SubscriptionRepository,
    UsageMeterRepository,
)
from app.rate_limit import limiter
from app.settings import settings

router = APIRouter(prefix="/api/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    tier: Literal["plus", "pro"]
    period: Literal["monthly", "yearly"] = "monthly"


class CheckoutResponse(BaseModel):
    checkout_url: str


class PlanInfo(BaseModel):
    slug: str
    name: str
    billing_period: str | None
    price_cents: int | None
    words_per_day: int
    uploads_per_day: int
    upload_bytes_per_day: int
    max_upload_bytes_per_import: int
    files_in_scope: int


class UsageInfo(BaseModel):
    usage_date: str
    ai_words: int
    uploads: int
    upload_bytes: int


class SubscriptionInfo(BaseModel):
    status: str
    plan_slug: str
    current_period_end: str | None
    cancel_at_period_end: bool


class BillingStatusResponse(BaseModel):
    plan: PlanInfo
    usage: UsageInfo
    subscription: SubscriptionInfo | None


def _plan_info(plan: PlanRow) -> PlanInfo:
    return PlanInfo(
        slug=plan.slug,
        name=plan.name,
        billing_period=plan.billing_period,
        price_cents=plan.price_cents,
        words_per_day=plan.words_per_day,
        uploads_per_day=plan.uploads_per_day,
        upload_bytes_per_day=plan.upload_bytes_per_day,
        max_upload_bytes_per_import=plan.max_upload_bytes_per_import,
        files_in_scope=plan.files_in_scope,
    )


@router.post("/checkout", response_model=CheckoutResponse)
@limiter.limit("10/minute")
async def create_checkout(
    request: Request,
    body: CheckoutRequest,
    claims: dict[str, Any] = Depends(require_session_token),
    plan_repo: PlanRepository = Depends(get_plan_repository),
) -> CheckoutResponse:
    """Create a hosted Dodo checkout for the requested plan variant."""
    user_id = claims.get("sub")
    email = claims.get("email")
    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An email is required to start a checkout — sign in with a Google account that has one.",
        )

    plan = await plan_repo.get_by_slug(f"{body.tier}_{body.period}")
    if plan is None or not plan.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown plan: {body.tier} ({body.period}).",
        )

    # One-time setup: create the four products in Dodo if they don't exist yet.
    if plan.dodo_product_id is None:
        try:
            product_ids = await run_in_threadpool(dodo.sync_subscription_products)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Dodo product setup failed: {exc}",
            ) from exc
        for slug, product_id in product_ids.items():
            await plan_repo.set_dodo_product_id_by_slug(slug, product_id)
        plan = await plan_repo.get_by_slug(plan.slug) or plan

    frontend = settings.frontend_base_url.rstrip("/")
    payload: dict[str, Any] = {
        "product_cart": [{"product_id": plan.dodo_product_id, "quantity": 1}],
        "customer": {
            "email": email,
            "name": claims.get("name"),
        },
        "return_url": f"{frontend}/app/billing?checkout=success",
        "cancel_url": f"{frontend}/app/billing?checkout=cancelled",
        "billing_currency": settings.dodo_billing_currency,
        "metadata": {"user_id": user_id, "plan_slug": plan.slug},
    }
    if settings.dodo_default_billing_country:
        payload["billing_address"] = {"country": settings.dodo_default_billing_country}
    if settings.dodo_trial_days > 0:
        payload["subscription_data"] = {"trial_period_days": settings.dodo_trial_days}

    try:
        checkout_url = await run_in_threadpool(dodo.create_checkout_session, payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dodo checkout failed: {exc}",
        ) from exc

    return CheckoutResponse(checkout_url=checkout_url)


@router.get("/status", response_model=BillingStatusResponse)
async def billing_status(
    claims: dict[str, Any] = Depends(require_session_token),
    plan_repo: PlanRepository = Depends(get_plan_repository),
    subscription_repo: SubscriptionRepository = Depends(get_subscription_repository),
    usage_repo: UsageMeterRepository = Depends(get_usage_meter_repository),
) -> BillingStatusResponse:
    """Current plan, entitlements, and today's usage for the signed-in user."""
    user_id = claims.get("sub", "")

    subscription = await subscription_repo.get_for_user(user_id)
    plan = await resolve_plan(plan_repo, subscription_repo, user_id)

    usage = await usage_repo.get_for_user_date(user_id, utc_today())

    sub_info: SubscriptionInfo | None = None
    if subscription is not None:
        sub_info = SubscriptionInfo(
            status=subscription.status,
            plan_slug=subscription.plan_slug,
            current_period_end=(
                subscription.current_period_end.isoformat()
                if subscription.current_period_end
                else None
            ),
            cancel_at_period_end=subscription.cancel_at_period_end,
        )

    return BillingStatusResponse(
        plan=_plan_info(plan),
        usage=UsageInfo(
            usage_date=(
                usage.usage_date.isoformat() if usage else utc_today().isoformat()
            ),
            ai_words=usage.ai_words if usage else 0,
            uploads=usage.uploads if usage else 0,
            upload_bytes=usage.upload_bytes if usage else 0,
        ),
        subscription=sub_info,
    )
