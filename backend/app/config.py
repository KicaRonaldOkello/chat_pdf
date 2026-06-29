import os
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_BACKEND_ROOT / ".env", override=False)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "120000"))

OLLAMA_OPENAI_BASE_URL = os.getenv(
    "OLLAMA_OPENAI_BASE_URL", f"{OLLAMA_BASE_URL}/v1"
).rstrip("/")
OLLAMA_OPENAI_API_KEY = os.getenv("OLLAMA_OPENAI_API_KEY", "ollama")

DATA_DIR = Path(
    os.getenv("CHATPDF_DATA_DIR", Path(__file__).resolve().parents[1] / "data")
).resolve()
DOCUMENTS_DIR = DATA_DIR / "documents"

QDRANT_URL = os.getenv("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "doc_chunks")
QDRANT_POINT_NAMESPACE = "b5b1f4ba-3a6a-4f4a-8b5f-1c4b9e0a0a01"

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")
VISION_MODEL = os.getenv("VISION_MODEL", "google/gemini-2.5-flash")

TABLE_DESCRIBER_MODEL = os.getenv("TABLE_DESCRIBER_MODEL", OLLAMA_MODEL)

METADATA_PROVIDER = os.getenv("METADATA_PROVIDER", "openrouter").lower()
METADATA_OPENROUTER_MODEL = os.getenv(
    "METADATA_OPENROUTER_MODEL", "openai/gpt-oss-120b"
)
METADATA_OPENROUTER_INPUT_TOKEN_BUDGET = int(
    os.getenv("METADATA_OPENROUTER_INPUT_TOKEN_BUDGET", "120000")
)
METADATA_MODEL = os.getenv("METADATA_MODEL", "phi4-mini")
METADATA_OLLAMA_BATCH_SIZE = int(
    os.getenv("METADATA_OLLAMA_BATCH_SIZE", os.getenv("METADATA_BATCH_SIZE", "1"))
)
METADATA_OLLAMA_SECTION_BODY_TOKENS = int(
    os.getenv("METADATA_OLLAMA_SECTION_BODY_TOKENS", "2000")
)
METADATA_CONCURRENCY = int(os.getenv("METADATA_CONCURRENCY", "2"))
METADATA_MAX_OUTPUT_TOKENS = int(os.getenv("METADATA_MAX_OUTPUT_TOKENS", "1024"))
METADATA_REQUEST_TIMEOUT = float(os.getenv("METADATA_REQUEST_TIMEOUT", "60"))

METADATA_OLLAMA_ENRICHMENT_TIMEOUT = float(
    os.getenv("METADATA_OLLAMA_ENRICHMENT_TIMEOUT", "180")
)
METADATA_DOC_META_OLLAMA_TIMEOUT = float(
    os.getenv("METADATA_DOC_META_OLLAMA_TIMEOUT", "90")
)
METADATA_OPENROUTER_ENRICHMENT_TIMEOUT = float(
    os.getenv("METADATA_OPENROUTER_ENRICHMENT_TIMEOUT", "180")
)
METADATA_OPENROUTER_ENRICHMENT_TEMPERATURE = float(
    os.getenv("METADATA_OPENROUTER_ENRICHMENT_TEMPERATURE", "0.1")
)
METADATA_LLM_TEMPERATURE = float(os.getenv("METADATA_LLM_TEMPERATURE", "0.1"))
METADATA_OLLAMA_BATCH_SECTION_SUMMARY_MAX = int(
    os.getenv("METADATA_OLLAMA_BATCH_SECTION_SUMMARY_MAX", "400")
)
METADATA_OLLAMA_BATCH_KEYWORDS_MAX = int(
    os.getenv("METADATA_OLLAMA_BATCH_KEYWORDS_MAX", "10")
)
METADATA_OPENROUTER_PARSED_SECTION_SUMMARY_MAX = int(
    os.getenv("METADATA_OPENROUTER_PARSED_SECTION_SUMMARY_MAX", "200")
)
METADATA_OPENROUTER_PARSED_KEYWORDS_MAX = int(
    os.getenv("METADATA_OPENROUTER_PARSED_KEYWORDS_MAX", "6")
)
METADATA_DOC_META_OPENING_CHARS = int(
    os.getenv("METADATA_DOC_META_OPENING_CHARS", "1500")
)

SLOW_UPSTREAM_REQUEST_TIMEOUT = float(os.getenv("SLOW_UPSTREAM_REQUEST_TIMEOUT", "120"))
QDRANT_CLIENT_TIMEOUT = int(os.getenv("QDRANT_CLIENT_TIMEOUT", "60"))
ROUTER_REQUEST_TIMEOUT = float(os.getenv("ROUTER_REQUEST_TIMEOUT", "60"))
JUDGE_REQUEST_TIMEOUT = float(os.getenv("JUDGE_REQUEST_TIMEOUT", "45"))
GUARDRAIL_REQUEST_TIMEOUT = float(os.getenv("GUARDRAIL_REQUEST_TIMEOUT", "20"))

CHUNK_TOKENS = int(os.getenv("CHUNK_TOKENS", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))

RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "8"))

MAX_DOCS_PER_CHAT = int(os.getenv("MAX_DOCS_PER_CHAT", "12"))

RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RERANK_RECALL_LIMIT = int(os.getenv("RERANK_RECALL_LIMIT", "48"))
RERANK_BATCH_SIZE = int(os.getenv("RERANK_BATCH_SIZE", "32"))
RERANK_ONLY_MULTIPLE = os.getenv("RERANK_ONLY_MULTIPLE", "false").lower() in (
    "1",
    "true",
    "yes",
)

GUARDRAIL_MODEL = os.getenv("GUARDRAIL_MODEL", "google/gemini-2.5-flash-lite")
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "openai/gpt-oss-120b")
ANSWERER_MODEL = os.getenv("ANSWERER_MODEL", "openai/gpt-oss-120b")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "google/gemini-2.5-flash-lite")

JUDGE_PASS_THRESHOLD = int(os.getenv("JUDGE_PASS_THRESHOLD", "7"))
AGENT_MAX_RETRIES = int(os.getenv("AGENT_MAX_RETRIES", "1"))

# Clerk session JWT verification (POST /api/users/sync, future protected routes)
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "").rstrip("/")
# Issuer claim, e.g. https://<your-instance>.clerk.accounts.dev (see Clerk dashboard → API keys)
CLERK_ISSUER = os.getenv("CLERK_ISSUER", "").rstrip("/")
# Optional. If set, the JWT `aud` claim is checked (Clerk "Authorized parties" / custom JWT template).
CLERK_JWT_AUDIENCE: str | None = os.getenv("CLERK_JWT_AUDIENCE", "").strip() or None

# CORS: comma-separated origins, e.g. "https://dxxxxx.cloudfront.net,https://app.example.com"
# If unset, defaults to local Angular dev servers only.
def _cors_origins() -> list[str]:
    raw = (os.getenv("CORS_ALLOW_ORIGINS") or "").strip()
    if not raw:
        return ["http://localhost:4200", "http://127.0.0.1:4200"]
    return [o.strip() for o in raw.split(",") if o.strip()]


CORS_ALLOW_ORIGINS: list[str] = _cors_origins()

# PostgreSQL (e.g. postgresql://lumen:lumen@127.0.0.1:5432/lumen) — `docker compose` in backend/
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Storage backend: "local" for dev (filesystem), "s3" for staging/production
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").strip()

S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
S3_KEY_PREFIX = os.getenv("S3_KEY_PREFIX", "documents").strip().strip("/") or "documents"

AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "")).strip() or "us-east-1"

MAX_PDF_UPLOAD_BYTES = int(os.getenv("MAX_PDF_UPLOAD_BYTES", str(5 * 1024 * 1024)))
