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
    if settings.storage_backend == "azure" and not settings.azure_storage_connection_string:
        raise RuntimeError(
            "AZURE_STORAGE_CONNECTION_STRING is empty; set it when using Azure storage backend."
        )
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

    # ── observability (optional — gated by env vars) ──────────────────────
    if settings.loki_enabled and settings.loki_url:
        from app.monitoring import setup_loki_logging

        setup_loki_logging(settings.loki_url, settings.loki_application_label)

    if settings.prometheus_enabled:
        from app.monitoring import setup_prometheus

        setup_prometheus(_app)

    if settings.otel_enabled and settings.otel_exporter_otlp_endpoint:
        from app.monitoring import _instrument_fastapi_app, setup_opentelemetry

        setup_opentelemetry(
            settings.otel_service_name, settings.otel_exporter_otlp_endpoint
        )
        _instrument_fastapi_app(_app)

    try:
        yield
    finally:
        app_runtime.db_session_maker = None
        await close_db_engine(getattr(_app.state, "db_engine", None))
        _app.state.db_engine = None
        _app.state.async_session_maker = None


app = FastAPI(title="Chat PDF API", lifespan=lifespan)

# ── security middleware ───────────────────────────────────────────────────────

_cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()] or [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting (in-memory, per-IP)
from slowapi import Limiter
from slowapi import _rate_limit_exceeded_handler as _rl_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rl_handler)


@app.middleware("http")
async def _add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = (
        "max-age=63072000; includeSubDomains; preload"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://accounts.google.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self'; "
        "connect-src 'self' https://openrouter.ai"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

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
