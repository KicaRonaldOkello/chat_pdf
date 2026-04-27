from contextlib import asynccontextmanager
from typing import Any

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

import app.runtime as app_runtime
from app import document_data, s3_storage
from app.api.chat import chat_stream_ndjson
from app.api.documents import search_hits_to_results
from app.api.schemas import (
    ChatRequest,
    SearchRequest,
    StatusResponse,
    UploadedFileItem,
    UploadResponse,
)
from app.auth.claims import email_from_claims
from app.auth.clerk_jwt import get_optional_clerk_session, require_clerk_session
from app.config import (
    ANSWERER_MODEL,
    CORS_ALLOW_ORIGINS,
    DATABASE_URL,
    EMBEDDING_MODEL,
    GUARDRAIL_MODEL,
    JUDGE_MODEL,
    MAX_PDF_UPLOAD_BYTES,
    METADATA_OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
    ROUTER_MODEL,
    S3_BUCKET,
)
from app.db import close_db_engine, open_db_engine
from app.db.dependencies import get_user_document_repository, get_user_repository
from app.db.repositories import (
    UserDocumentRepository,
    UserRepository,
    UserRow,
)
from app.processing.embeddings import embed_query
from app.processing.pipeline import process_document
from app.processing.vectorstore import search as vector_search


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not S3_BUCKET:
        raise RuntimeError("S3_BUCKET is empty; set S3_BUCKET in the environment.")
    if not (DATABASE_URL or "").strip():
        raise RuntimeError(
            "DATABASE_URL is required: document state (status, tree, meta) is stored in PostgreSQL."
        )
    opened = await open_db_engine()
    if opened is None:
        raise RuntimeError("Failed to open the database engine (check DATABASE_URL).")
    _app.state.db_engine, _app.state.async_session_maker = opened
    app_runtime.db_session_maker = _app.state.async_session_maker
    try:
        yield
    finally:
        app_runtime.db_session_maker = None
        await close_db_engine(getattr(_app.state, "db_engine", None))
        _app.state.db_engine = None
        _app.state.async_session_maker = None


app = FastAPI(title="Chat PDF API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UserSyncResponse(BaseModel):
    clerk_user_id: str
    email: str | None
    created_at: str
    last_seen_at: str


@app.post("/api/users/sync", response_model=UserSyncResponse, tags=["auth"])
async def sync_user(
    user_repo: UserRepository = Depends(get_user_repository),
    claims: dict[str, Any] = Depends(require_clerk_session),
) -> UserSyncResponse:
    """Idempotent: upsert the signed-in Clerk user; call after sign-in with Bearer session token."""
    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token missing `sub`",
        )
    email = email_from_claims(claims)
    user: UserRow = await user_repo.upsert_clerk_user(sub, email)
    return UserSyncResponse(
        clerk_user_id=user.clerk_user_id,
        email=user.email,
        created_at=user.created_at.isoformat(),
        last_seen_at=user.last_seen_at.isoformat(),
    )


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


class RecentDocumentItem(BaseModel):
    document_id: str
    filename: str
    uploaded_at: str
    file_size_bytes: int | None = None


@app.get("/api/documents/recent", response_model=list[RecentDocumentItem], tags=["documents"])
async def list_recent_documents(
    user_doc_repo: UserDocumentRepository = Depends(get_user_document_repository),
    claims: dict[str, Any] = Depends(require_clerk_session),
    limit: int = Query(3, ge=1, le=50),
) -> list[RecentDocumentItem]:
    """Last uploaded PDFs for the signed-in Clerk user (for Home recents)."""
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


@app.get("/api/documents/uploaded", response_model=list[UploadedFileItem], tags=["documents"])
async def list_uploaded_files(
    user_doc_repo: UserDocumentRepository = Depends(get_user_document_repository),
    claims: dict[str, Any] = Depends(require_clerk_session),
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


@app.get("/api/documents/{doc_id}/file", tags=["documents"])
async def get_document_pdf_file(
    doc_id: str,
    user_doc_repo: UserDocumentRepository = Depends(get_user_document_repository),
    claims: dict[str, Any] = Depends(require_clerk_session),
) -> StreamingResponse:
    """Stream the PDF for a document the user owns from S3."""
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

    from botocore.exceptions import ClientError

    try:
        obj = s3_storage.get_object_streaming(doc_id)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            raise HTTPException(
                status_code=404, detail="PDF not found in storage"
            ) from e
        raise HTTPException(
            status_code=502, detail="Could not read PDF from storage"
        ) from e

    def stream() -> Any:
        yield from obj["Body"].iter_chunks(chunk_size=65_536)

    return StreamingResponse(
        stream(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.post("/api/upload", response_model=UploadResponse)
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

    doc_id = await document_data.save_upload_to_s3_and_db(data, file.filename)
    await _record_user_upload(request, claims, doc_id, file.filename, len(data))
    background_tasks.add_task(process_document, doc_id)
    return UploadResponse(
        document_id=doc_id, status="processing", filename=file.filename
    )


@app.get("/api/documents/{doc_id}/status", response_model=StatusResponse)
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


@app.get("/api/documents/{doc_id}/tree")
async def document_tree(doc_id: str) -> JSONResponse:
    t = await document_data.get_tree(doc_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Tree not available yet")
    return JSONResponse(content=t)


@app.get("/api/documents/{doc_id}/sections")
async def document_sections(doc_id: str) -> JSONResponse:
    idx = await document_data.get_sections_index(doc_id)
    if idx is None:
        raise HTTPException(status_code=404, detail="Sections index not available yet")
    return JSONResponse(content=idx)


@app.get("/api/documents/{doc_id}/meta")
async def document_meta(doc_id: str) -> JSONResponse:
    m = await document_data.get_document_meta(doc_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Document meta not available yet")
    return JSONResponse(content=m)


@app.get("/api/documents/{doc_id}/traces")
async def document_traces(doc_id: str) -> JSONResponse:
    return JSONResponse(
        content=await document_data.list_traces(doc_id)
    )


@app.post("/api/documents/{doc_id}/search")
async def document_search(doc_id: str, body: SearchRequest) -> JSONResponse:
    status = await document_data.get_status(doc_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Unknown document_id")
    if status.status != "ready":
        progress_pct = int(status.progress * 100)
        raise HTTPException(
            status_code=409,
            detail=f"Document not ready ({status.stage}, {progress_pct}%)",
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


@app.post("/api/chat/stream")
async def chat_stream(body: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        chat_stream_ndjson(body),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/api/documents/{doc_id}")
async def delete_document(request: Request, doc_id: str) -> dict[str, str]:
    from app.processing import vectorstore

    try:
        await vectorstore.delete_doc(doc_id)
    except Exception:
        pass
    try:
        s3_storage.delete_all_for_document(doc_id)
    except Exception:
        pass
    await document_data.delete_document_artifacts(doc_id)
    await _delete_user_document_row(request, doc_id)
    return {"status": "deleted", "document_id": doc_id}


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "llm_provider": "openrouter",
        "openrouter_base_url": OPENROUTER_BASE_URL,
        "guardrail": GUARDRAIL_MODEL,
        "router": ROUTER_MODEL,
        "answerer": ANSWERER_MODEL,
        "judge": JUDGE_MODEL,
        "metadata": METADATA_OPENROUTER_MODEL,
        "embeddings": f"{EMBEDDING_MODEL} (ollama, local)",
    }
