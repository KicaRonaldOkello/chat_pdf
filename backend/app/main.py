from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app import store
from app.api.chat import chat_stream_ndjson
from app.api.documents import search_hits_to_results
from app.api.schemas import (
    ChatRequest,
    SearchRequest,
    StatusResponse,
    UploadResponse,
)
from app.config import (
    ANSWERER_MODEL,
    EMBEDDING_MODEL,
    GUARDRAIL_MODEL,
    JUDGE_MODEL,
    METADATA_OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
    ROUTER_MODEL,
)
from app.processing.embeddings import embed_query
from app.processing.pipeline import process_document
from app.processing.vectorstore import search as vector_search

app = FastAPI(title="Chat PDF API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/upload", response_model=UploadResponse)
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Expected a PDF file")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    doc_id = store.save_upload(data, file.filename)
    background_tasks.add_task(process_document, doc_id)
    return UploadResponse(
        document_id=doc_id, status="processing", filename=file.filename
    )


@app.get("/api/documents/{doc_id}/status", response_model=StatusResponse)
async def document_status(doc_id: str) -> StatusResponse:
    s = store.get_status(doc_id)
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
    t = store.get_tree(doc_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Tree not available yet")
    return JSONResponse(content=t)


@app.get("/api/documents/{doc_id}/sections")
async def document_sections(doc_id: str) -> JSONResponse:
    idx = store.get_sections_index(doc_id)
    if idx is None:
        raise HTTPException(status_code=404, detail="Sections index not available yet")
    return JSONResponse(content=idx)


@app.get("/api/documents/{doc_id}/meta")
async def document_meta(doc_id: str) -> JSONResponse:
    m = store.get_document_meta(doc_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Document meta not available yet")
    return JSONResponse(content=m)


@app.get("/api/documents/{doc_id}/traces")
async def document_traces(doc_id: str) -> JSONResponse:
    return JSONResponse(content=store.list_traces(doc_id))


@app.post("/api/documents/{doc_id}/search")
async def document_search(doc_id: str, body: SearchRequest) -> JSONResponse:
    status = store.get_status(doc_id)
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
async def delete_document(doc_id: str) -> dict[str, str]:
    from app.processing import vectorstore

    try:
        await vectorstore.delete_doc(doc_id)
    except Exception:
        pass
    store.delete_document(doc_id)
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
