"""add worker-queue columns to document_state (attempts, next_attempt_at, claimed_until)

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision: str = "0007"
branch_labels = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "document_state",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "document_state",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "document_state",
        sa.Column("claimed_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_state", "claimed_until")
    op.drop_column("document_state", "next_attempt_at")
    op.drop_column("document_state", "attempts")
