"""Routes under ``/api/documents`` — document CRUD, status, search, file streaming."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from app import document_data
from app.api.documents import search_hits_to_results
from app.api.schemas import SearchRequest, StatusResponse, UploadedFileItem
from app.auth.google_auth import require_session_token
from app.db.dependencies import get_user_document_repository
from app.db.repositories import UserDocumentRepository
from app.processing.embeddings import embed_query
from app.processing.vectorstore import search as vector_search
from app.storage import get_storage

router = APIRouter(prefix="/api/documents", tags=["documents"])


# ── helpers ──────────────────────────────────────────────────────────────────


async def _store_display_for_uploaded(doc_id: str) -> tuple[str, str]:
    """Return (processing_status, display_status) for library UI chips."""
    s = await document_data.get_status(doc_id)
    if s is None:
        return "unknown", "unknown"
    st = s.status
    if st == "ready":
        return st, "analyzed"
    if st == "error":
        return st, "error"
    return st, "processing"


async def _delete_user_document_row(request: Request, document_id: str) -> None:
    sm = getattr(request.app.state, "async_session_maker", None)
    if sm is None:
        return
    session = sm()
    try:
        await UserDocumentRepository(session).delete_by_document_id(document_id)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ── models ───────────────────────────────────────────────────────────────────


class RecentDocumentItem(BaseModel):
    document_id: str
    filename: str
    uploaded_at: str
    file_size_bytes: int | None = None


# ── routes ───────────────────────────────────────────────────────────────────


@router.get("/recent", response_model=list[RecentDocumentItem])
async def list_recent_documents(
    user_doc_repo: UserDocumentRepository = Depends(get_user_document_repository),
    claims: dict[str, Any] = Depends(require_session_token),
    limit: int = Query(3, ge=1, le=50),
) -> list[RecentDocumentItem]:
    """Last uploaded PDFs for the signed-in user (for Home recents)."""
    sub = claims.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token missing `sub`",
        )
    rows = await user_doc_repo.list_recent(sub, limit)
    return [
        RecentDocumentItem(
            document_id=r.document_id,
            filename=r.filename,
            uploaded_at=r.uploaded_at.isoformat(),
            file_size_bytes=r.file_size_bytes,
        )
        for r in rows
    ]


@router.get("/uploaded", response_model=list[UploadedFileItem])
async def list_uploaded_files(
    user_doc_repo: UserDocumentRepository = Depends(get_user_document_repository),
    claims: dict[str, Any] = Depends(require_session_token),
    limit: int = Query(200, ge=1, le=500),
) -> list[UploadedFileItem]:
    """All PDFs recorded for the signed-in user (newest first; processing status from Postgres)."""
    sub = claims.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token missing `sub`",
        )
    rows = await user_doc_repo.list_for_user(sub, limit)
    out: list[UploadedFileItem] = []
    for r in rows:
        raw, disp = await _store_display_for_uploaded(r.document_id)
        out.append(
            UploadedFileItem(
                document_id=r.document_id,
                filename=r.filename,
                uploaded_at=r.uploaded_at.isoformat(),
                file_size_bytes=r.file_size_bytes,
                processing_status=raw,
                display_status=disp,
            )
        )
    return out


@router.get("/{doc_id}/file")
async def get_document_pdf_file(
    doc_id: str,
    user_doc_repo: UserDocumentRepository = Depends(get_user_document_repository),
    claims: dict[str, Any] = Depends(require_session_token),
) -> StreamingResponse:
    """Stream the PDF for a document the user owns from storage."""
    sub = claims.get("sub")
    if not isinstance(sub, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token missing `sub`",
        )
    if not await user_doc_repo.is_owner(sub, doc_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not allowed for this document",
        )
    st = await document_data.get_status(doc_id)
    if st is None:
        raise HTTPException(status_code=404, detail="Unknown document_id")
    filename = (st.filename or "document.pdf").replace('"', "")

    try:
        chunks = get_storage().get_source_pdf_streaming(doc_id)
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=404, detail="PDF not found in storage"
        ) from err
    except Exception as err:
        raise HTTPException(
            status_code=502, detail="Could not read PDF from storage"
        ) from err

    def stream() -> Any:
        yield from chunks

    return StreamingResponse(
        stream(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/{doc_id}/status", response_model=StatusResponse)
async def document_status(doc_id: str) -> StatusResponse:
    s = await document_data.get_status(doc_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Unknown document_id")
    return StatusResponse(
        document_id=doc_id,
        status=s.status,
        stage=s.stage,
        progress=s.progress,
        filename=s.filename,
        num_pages=s.num_pages,
        error=s.error,
        warnings=s.warnings,
    )


@router.get("/{doc_id}/tree")
async def document_tree(doc_id: str) -> JSONResponse:
    t = await document_data.get_tree(doc_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Tree not available yet")
    return JSONResponse(content=t)


@router.get("/{doc_id}/sections")
async def document_sections(doc_id: str) -> JSONResponse:
    idx = await document_data.get_sections_index(doc_id)
    if idx is None:
        raise HTTPException(status_code=404, detail="Sections index not available yet")
    return JSONResponse(content=idx)


@router.get("/{doc_id}/meta")
async def document_meta(doc_id: str) -> JSONResponse:
    m = await document_data.get_document_meta(doc_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Document meta not available yet")
    return JSONResponse(content=m)


@router.get("/{doc_id}/traces")
async def document_traces(doc_id: str) -> JSONResponse:
    return JSONResponse(
        content=await document_data.list_traces(doc_id)
    )


@router.post("/{doc_id}/search")
async def document_search(doc_id: str, body: SearchRequest) -> JSONResponse:
    status_ = await document_data.get_status(doc_id)
    if status_ is None:
        raise HTTPException(status_code=404, detail="Unknown document_id")
    if status_.status != "ready":
        progress_pct = int(status_.progress * 100)
        raise HTTPException(
            status_code=409,
            detail=f"Document not ready ({status_.stage}, {progress_pct}%)",
        )

    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Empty query")

    vector = await embed_query(query)
    if not vector:
        raise HTTPException(
            status_code=502, detail="Embedding backend returned empty vector"
        )

    hits = await vector_search(doc_id, vector, body.top_k)
    return JSONResponse(content={"results": search_hits_to_results(hits)})


@router.delete("/{doc_id}")
async def delete_document(request: Request, doc_id: str) -> dict[str, str]:
    from app.processing import vectorstore

    try:
        await vectorstore.delete_doc(doc_id)
    except Exception:
        pass
    try:
        get_storage().delete_all_for_document(doc_id)
    except Exception:
        pass
    await document_data.delete_document_artifacts(doc_id)
    await _delete_user_document_row(request, doc_id)
    return {"status": "deleted", "document_id": doc_id}
