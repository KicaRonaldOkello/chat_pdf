"""Application settings using Pydantic for type-safe configuration."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Ollama
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:e4b"
    max_context_chars: int = 120000
    ollama_openai_base_url: str = ""
    ollama_openai_api_key: str = "ollama"

    # Data directories
    chatpdf_data_dir: Path = _BACKEND_ROOT / "data"
    documents_dir: Path = Field(
        default_factory=lambda: _BACKEND_ROOT / "data" / "documents"
    )

    # Embeddings
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768

    # OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Vision
    vision_model: str = "google/gemini-2.5-flash"

    # Metadata processing
    metadata_provider: Literal["openrouter", "ollama"] = "openrouter"
    metadata_openrouter_model: str = "openai/gpt-oss-120b"
    metadata_model: str = "phi4-mini"
    metadata_ollama_batch_size: int = 1
    metadata_ollama_section_body_tokens: int = 2000
    metadata_concurrency: int = 2
    metadata_max_output_tokens: int = 1024
    metadata_request_timeout: float = 60.0
    metadata_ollama_enrichment_timeout: float = 180.0
    metadata_doc_meta_ollama_timeout: float = 90.0
    metadata_openrouter_enrichment_timeout: float = 180.0
    #: Hard cap on one document's metadata enrichment, so a flaky provider can
    #: degrade metadata quality without occupying the worker for an hour.
    metadata_openrouter_enrichment_deadline_seconds: float = 600.0
    metadata_openrouter_enrichment_temperature: float = 0.1
    metadata_llm_temperature: float = 0.1
    metadata_ollama_batch_section_summary_max: int = 400
    metadata_ollama_batch_keywords_max: int = 10
    metadata_openrouter_parsed_section_summary_max: int = 200
    metadata_openrouter_parsed_keywords_max: int = 6
    metadata_doc_meta_opening_chars: int = 1500
    metadata_openrouter_input_token_budget: int = 120000

    # Legacy Ollama metadata model (fallback)
    table_describer_model: str = "openai/gpt-oss-120b"

    # Timeouts
    slow_upstream_request_timeout: float = 120.0
    router_request_timeout: float = 60.0
    judge_request_timeout: float = 45.0
    guardrail_request_timeout: float = 20.0

    # Chunking
    chunk_tokens: int = 800
    chunk_overlap: int = 100

    # Retrieval
    retrieval_top_k: int = 8
    max_docs_per_chat: int = 12

    # Vector index
    vector_index_lists: int = 100

    # Reranking
    rerank_enabled: bool = True
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_recall_limit: int = 48
    rerank_batch_size: int = 32
    rerank_only_multiple: bool = False

    # Agent models
    guardrail_model: str = "google/gemini-2.5-flash-lite"
    router_model: str = "google/gemini-2.5-flash-lite"
    router_reasoning_effort: Literal["high", "medium", "low"] = "low"
    answerer_model: str = "google/gemini-3.1-flash-lite"
    judge_model: str = "google/gemini-2.5-flash-lite"

    # Agent behavior
    judge_pass_threshold: int = 7
    agent_max_retries: int = 1
    retrieval_max_retries: int = 2

    # Vision
    image_auto_vision_score: float = 0.75

    # Google & Session JWT auth
    google_client_id: str = ""
    google_client_secret: str = ""
    jwt_secret: str = ""  # REQUIRED — set in .env for all environments
    jwt_expires_days: int = 30

    # CORS — comma-separated in env, e.g. CORS_ALLOW_ORIGINS="https://understandingnotes.com,https://www.understandingnotes.com"
    cors_allow_origins: str = ""
    # Public origin of the Angular app — used for Dodo checkout return/cancel URLs.
    frontend_base_url: str = "http://localhost:4200"

    # Database
    database_url: str = ""

    # Storage
    storage_backend: Literal["local", "s3", "azure"] = "local"
    s3_bucket: str = ""
    s3_key_prefix: str = "documents"
    aws_region: str = "us-east-1"
    azure_storage_container_name: str = "chatpdfs"
    azure_storage_connection_string: str = ""

    # Loki log shipping (optional — set LOKI_ENABLED=true and LOKI_URL to activate)
    loki_url: str = ""  # e.g. "http://localhost:3100"
    loki_enabled: bool = False
    loki_application_label: str = "understanding-notes-backend"

    # Prometheus metrics endpoint (optional — set PROMETHEUS_ENABLED=true)
    prometheus_enabled: bool = False

    # OpenTelemetry (optional — set OTEL_ENABLED=true)
    otel_enabled: bool = False
    otel_service_name: str = "understanding-notes-backend"
    otel_exporter_otlp_endpoint: str = ""  # e.g. "http://localhost:4318"

    # Dodo Payments (billing / subscriptions)
    dodo_api_key: str = ""  # test or live API key from the Dodo dashboard
    dodo_webhook_secret: str = ""  # webhook signing secret (test/live)
    dodo_mode: Literal["test_mode", "live_mode"] = "test_mode"
    dodo_webhook_url: str = ""  # e.g. "https://api.example.com/webhooks/dodo"
    dodo_billing_currency: str = "USD"  # locked at first charge — must match checkout
    dodo_trial_days: int = 0
    dodo_default_billing_country: str = ""  # ISO 3166-1 alpha-2, e.g. "US"

    # Upload limits
    max_pdf_upload_bytes: int = 5 * 1024 * 1024

    # PDF input / resource safeguards
    max_pdf_pages: int = 500
    max_pdf_decompressed_bytes: int = 256 * 1024 * 1024
    max_pdf_images: int = 2000
    processing_timeout_seconds: float = 1800.0

    # Ingestion worker queue
    worker_concurrency: int = 2
    parse_concurrency: int = 2
    embedding_concurrency: int = 4
    worker_poll_interval_seconds: float = 5.0
    worker_claim_timeout_seconds: float = 1800.0
    worker_max_attempts: int = 3
    worker_retry_base_seconds: float = 60.0
    table_llm_concurrency: int = 2

    # Table detection and description retries
    table_page_pipe_min_lines: int = 3
    table_page_numeric_min_lines: int = 2
    table_page_line_min_len: int = 12
    table_describer_max_retries: int = 2
    table_describer_retry_base_seconds: float = 1.0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Post-processing for derived values
        if not self.ollama_openai_base_url:
            self.ollama_openai_base_url = f"{self.ollama_base_url.rstrip('/')}/v1"
        self.documents_dir = Path(self.chatpdf_data_dir) / "documents"

    @classmethod
    def override(cls, **overrides) -> "Settings":
        """Create a temporary instance with overridden values for tests.

        Usage::

            with patch("app.settings.settings", Settings.override(database_url="test")):
                ...
        """
        return cls(**overrides)


settings = Settings()
