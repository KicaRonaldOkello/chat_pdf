"""FastAPI application factory for the Chat PDF backend.

Domain routes live in ``app.api.routes.*`` — this module only creates the app and
wires together middleware, lifespan, and routers.
"""

import logging
import sys
from contextlib import asynccontextmanager

# Ensure journey + agent logs are visible in the terminal.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-40s  %(levelname)-8s  %(message)s",
    stream=sys.stderr,
)
# Keep noisy libraries at WARNING
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
# Ensure agent + journey logs are visible
logging.getLogger("app.agents").setLevel(logging.INFO)
logging.getLogger("app.processing").setLevel(logging.INFO)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

import app.runtime as app_runtime
from app.api.routes import auth, chat, documents, upload
from app.db import close_db_engine, open_db_engine
from app.settings import settings

log = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.storage_backend == "s3" and not settings.s3_bucket:
        raise RuntimeError("S3_BUCKET is empty; set S3_BUCKET in the environment when using S3 storage backend.")
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is required: document state (status, tree, meta) is stored in PostgreSQL."
        )
    opened = await open_db_engine()
    if opened is None:
        raise RuntimeError("Failed to open the database engine (check DATABASE_URL).")
    _app.state.db_engine, _app.state.async_session_maker = opened
    app_runtime.db_session_maker = _app.state.async_session_maker

    # Test database connection on startup
    try:
        async with _app.state.db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        success_msg = f"✓ Database connection successful! (Backend: {settings.storage_backend})"
        log.info(success_msg)
        print(success_msg)
    except Exception as e:
        log.error(f"Database connection failed: {e}")
        raise RuntimeError(f"Failed to connect to database: {e}") from e

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
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── domain routers ───────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(upload.router)
app.include_router(chat.router)


# ── health ───────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "llm_provider": "openrouter",
        "openrouter_base_url": settings.openrouter_base_url,
        "guardrail": settings.guardrail_model,
        "router": settings.router_model,
        "answerer": settings.answerer_model,
        "judge": settings.judge_model,
        "metadata": settings.metadata_openrouter_model,
        "embeddings": f"{settings.embedding_model} (ollama, local)",
    }
