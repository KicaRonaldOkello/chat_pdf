"""add user_documents (per-user upload history for recents)

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision: str = "0001"
branch_labels = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "user_documents",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("clerk_user_id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["clerk_user_id"],
            ["users.clerk_user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_user_documents_document_id"),
    )
    op.create_index(
        "ix_user_documents_clerk_user_uploaded",
        "user_documents",
        ["clerk_user_id", "uploaded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_documents_clerk_user_uploaded", table_name="user_documents")
    op.drop_table("user_documents")
