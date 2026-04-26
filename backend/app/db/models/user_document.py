from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class UserDocument(Base):
    """One row per uploaded `document_id` in the filesystem store, scoped to a Clerk user."""

    __tablename__ = "user_documents"
    __table_args__ = (Index("ix_user_documents_clerk_user_uploaded", "clerk_user_id", "uploaded_at"),)

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    clerk_user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.clerk_user_id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
