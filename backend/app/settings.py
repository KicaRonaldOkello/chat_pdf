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
    documents_dir: Path = Field(default_factory=lambda: _BACKEND_ROOT / "data" / "documents")

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

    # Clerk auth
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    clerk_jwt_audience: str | None = None

    # CORS
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:4200", "http://127.0.0.1:4200"]
    )

    # Database
    database_url: str = ""

    # Storage
    storage_backend: Literal["local", "s3"] = "local"
    s3_bucket: str = ""
    s3_key_prefix: str = "documents"
    aws_region: str = "us-east-1"

    # Upload limits
    max_pdf_upload_bytes: int = 5 * 1024 * 1024

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
