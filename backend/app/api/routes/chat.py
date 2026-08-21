"""Routes under ``/api/chat`` — streaming chat endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.chat import chat_stream_ndjson
from app.api.documents import resolve_chat_document_ids
from app.api.schemas import ChatRequest
from app.auth.google_auth import require_session_token
from app.dates import utc_today
from app.billing.enforcement import (
    check_files_in_scope,
    check_word_quota,
    chat_stream_with_usage,
    resolve_plan,
)
from app.db.dependencies import (
    get_plan_repository,
    get_subscription_repository,
    get_usage_meter_repository,
)
from app.db.repositories import (
    PlanRepository,
    SubscriptionRepository,
    UsageMeterRepository,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    claims: dict[str, Any] = Depends(require_session_token),
    plan_repo: PlanRepository = Depends(get_plan_repository),
    subscription_repo: SubscriptionRepository = Depends(get_subscription_repository),
    usage_repo: UsageMeterRepository = Depends(get_usage_meter_repository),
) -> StreamingResponse:
    user_id = claims.get("sub", "")
    plan = await resolve_plan(plan_repo, subscription_repo, user_id)
    usage = await usage_repo.get_for_user_date(user_id, utc_today())
    doc_ids = resolve_chat_document_ids(body)
    check_files_in_scope(plan, len(doc_ids))
    check_word_quota(plan, usage)
    return StreamingResponse(
        chat_stream_with_usage(
            body,
            plan,
            usage,
            usage_repo,
            user_id,
            session_maker=getattr(request.app.state, "async_session_maker", None),
        ),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
