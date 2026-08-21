from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UsageMeter(Base):
    """Daily usage rollup per user (AI words, uploads, upload bytes)."""

    __tablename__ = "usage_meter"
    __table_args__ = (
        UniqueConstraint("user_id", "usage_date", name="uq_usage_meter_user_date"),
        Index("ix_usage_meter_user_date", "user_id", "usage_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    ai_words: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    uploads: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    upload_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
