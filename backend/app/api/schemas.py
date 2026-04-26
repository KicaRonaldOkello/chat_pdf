from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.api.documents import resolve_chat_document_ids


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    document_id: str | None = None
    document_ids: list[str] | None = None

    @model_validator(mode="after")
    def require_document_scope(self) -> ChatRequest:
        resolve_chat_document_ids(self)
        return self


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(8, ge=1, le=50)


class UploadResponse(BaseModel):
    document_id: str
    status: str
    filename: str


class UploadedFileItem(BaseModel):
    document_id: str
    filename: str
    uploaded_at: str
    file_size_bytes: int | None
    processing_status: str = Field(
        ...,
        description="Pipeline status from disk: queued, extracting, …, ready, error, or unknown.",
    )
    display_status: str = Field(
        ...,
        description="UI chip: analyzed, processing, error, unknown.",
    )


class StatusResponse(BaseModel):
    document_id: str
    status: str
    stage: str
    progress: float
    filename: str
    num_pages: int | None = None
    error: str | None = None
    warnings: list[str] | None = None
