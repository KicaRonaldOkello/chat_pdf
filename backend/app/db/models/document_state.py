from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentState(Base):
    """JSON blobs for processing state; PDF is in S3, vectors in Qdrant."""

    __tablename__ = "document_state"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # status_payload mirrors DocumentStatus (status, stage, progress, filename, error, num_pages, warnings)
    status_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tree: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    sections_index: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    document_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # Newest trace first; app caps length on append
    traces: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
