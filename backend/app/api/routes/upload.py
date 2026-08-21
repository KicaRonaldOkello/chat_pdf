"""Routes under ``/api/upload`` — PDF upload endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)

from app import document_data
from app.api.schemas import UploadResponse
from app.auth.google_auth import require_session_token
from app.billing.enforcement import check_upload_quota, resolve_plan
from app.dates import utc_today
from app.db.dependencies import (
    get_plan_repository,
    get_subscription_repository,
    get_usage_meter_repository,
)
from app.db.repositories import (
    PlanRepository,
    SubscriptionRepository,
    UsageMeterRepository,
    UserDocumentRepository,
)
from app.processing.validation import validate_pdf_bytes
from app.settings import settings

router = APIRouter(prefix="/api", tags=["upload"])


async def _record_user_upload(
    request: Request,
    claims: dict[str, Any] | None,
    document_id: str,
    filename: str,
    file_size: int,
) -> None:
    if not claims:
        return
    sub = claims.get("sub")
    if not isinstance(sub, str):
        return
    sm = getattr(request.app.state, "async_session_maker", None)
    if sm is None:
        return
    session = sm()
    try:
        await UserDocumentRepository(session).record_upload(
            sub, document_id, filename, file_size
        )
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@router.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    claims: dict[str, Any] = Depends(require_session_token),
    plan_repo: PlanRepository = Depends(get_plan_repository),
    subscription_repo: SubscriptionRepository = Depends(get_subscription_repository),
    usage_repo: UsageMeterRepository = Depends(get_usage_meter_repository),
) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Expected a PDF file")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    user_id = claims.get("sub", "")
    plan = await resolve_plan(plan_repo, subscription_repo, user_id)
    usage = await usage_repo.get_for_user_date(user_id, utc_today())
    check_upload_quota(plan, usage, extra_bytes=len(data))

    max_import = plan.max_upload_bytes_per_import or settings.max_pdf_upload_bytes
    if len(data) > max_import:
        mb = max_import // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"PDF must be at most {mb} MB on your current plan",
        )
    inspection = validate_pdf_bytes(data)
    if not inspection.is_pdf:
        raise HTTPException(
            status_code=400,
            detail="File is not a valid PDF (missing %PDF header)",
        )
    if not inspection.readable:
        raise HTTPException(
            status_code=400,
            detail="File could not be read as a PDF; it may be corrupt",
        )

    doc_id = await document_data.save_upload_and_record(data, file.filename)
    await _record_user_upload(request, claims, doc_id, file.filename, len(data))
    await usage_repo.increment(
        user_id, utc_today(), uploads=1, upload_bytes=len(data)
    )
    return UploadResponse(
        document_id=doc_id, status="processing", filename=file.filename
    )
