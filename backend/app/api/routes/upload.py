"""Routes under ``/api/upload`` — PDF upload endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile, status

from app import document_data
from app.api.schemas import UploadResponse
from app.auth.clerk_jwt import get_optional_clerk_session
from app.config import MAX_PDF_UPLOAD_BYTES
from app.db.repositories import UserDocumentRepository
from app.processing.pipeline import process_document

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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    claims: dict[str, Any] | None = Depends(get_optional_clerk_session),
) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Expected a PDF file")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_PDF_UPLOAD_BYTES:
        mb = MAX_PDF_UPLOAD_BYTES // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"PDF must be at most {mb} MB",
        )

    doc_id = await document_data.save_upload_and_record(data, file.filename)
    await _record_user_upload(request, claims, doc_id, file.filename, len(data))
    background_tasks.add_task(process_document, doc_id)
    return UploadResponse(
        document_id=doc_id, status="processing", filename=file.filename
    )
