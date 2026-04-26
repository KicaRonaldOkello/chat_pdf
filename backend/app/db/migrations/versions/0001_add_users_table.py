"""add users (Clerk id, email, timestamps)

Revision ID: 0001
Revises:
Create Date: 2026-04-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision: str | None = None
branch_labels = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("clerk_user_id", sa.String(), primary_key=True, nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_users_last_seen", "users", ["last_seen_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_last_seen", table_name="users")
    op.drop_table("users")
