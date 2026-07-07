"""add document_chunks table with pgvector

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("section_path", sa.Text(), nullable=False, server_default="(root)"),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("display_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("element_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("page_size", sa.JSON(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("chunk_id"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document_state.document_id"],
            ondelete="CASCADE",
        ),
    )

    # pgvector column must be added via raw SQL
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN embedding vector(768) NOT NULL"
    )

    op.create_index(
        "ix_document_chunks_doc",
        "document_chunks",
        ["document_id"],
    )
    op.create_index(
        "ix_document_chunks_doc_section",
        "document_chunks",
        ["document_id", "section_path"],
    )
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_embedding_hnsw")
    op.drop_index("ix_document_chunks_doc_section")
    op.drop_index("ix_document_chunks_doc")
    op.drop_table("document_chunks")
