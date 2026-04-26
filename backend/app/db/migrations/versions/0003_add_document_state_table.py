"""add document_state (tree, status, meta in Postgres; PDF remains S3)

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision: str = "0002"
branch_labels = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "document_state",
        sa.Column("document_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("status_payload", postgresql.JSONB, nullable=False),
        sa.Column("tree", postgresql.JSONB, nullable=True),
        sa.Column("sections_index", postgresql.JSONB, nullable=True),
        sa.Column("document_meta", postgresql.JSONB, nullable=True),
        sa.Column(
            "traces",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_document_state_updated_at", "document_state", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_document_state_updated_at", table_name="document_state")
    op.drop_table("document_state")
