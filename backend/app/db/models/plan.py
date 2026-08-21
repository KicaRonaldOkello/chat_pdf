from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Plan(Base):
    """One row per billable plan variant (Free, Plus monthly/yearly, Pro monthly/yearly).

    A limit value of -1 means "unlimited". `dodo_product_id` is populated when the
    products are created in the Dodo dashboard (Phase 1); it is null for Free.
    """

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    billing_period: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # "monthly" | "yearly" | None for Free
    dodo_product_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    words_per_day: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploads_per_day: Mapped[int] = mapped_column(Integer, nullable=False)
    upload_bytes_per_day: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_upload_bytes_per_import: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=str(5 * 1024 * 1024)
    )
    files_in_scope: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
