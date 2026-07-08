"""rename_clerk_user_id

Revision ID: bfb9db12e95c
Revises: 0004
Create Date: 2026-07-07 13:37:57.943483

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bfb9db12e95c'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop foreign key constraint on user_documents
    op.drop_constraint(
        "user_documents_clerk_user_id_fkey",
        "user_documents",
        type_="foreignkey",
    )

    # 2. Drop old index on user_documents
    op.drop_index("ix_user_documents_clerk_user_uploaded", "user_documents")

    # 3. Rename columns
    op.alter_column("users", "clerk_user_id", new_column_name="user_id")
    op.alter_column("user_documents", "clerk_user_id", new_column_name="user_id")

    # 4. Re-create index with new column name
    op.create_index(
        "ix_user_documents_user_uploaded",
        "user_documents",
        ["user_id", "uploaded_at"],
    )

    # 5. Re-create foreign key referencing users.user_id
    op.create_foreign_key(
        "user_documents_user_id_fkey",
        "user_documents",
        "users",
        ["user_id"],
        ["user_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # 1. Drop new foreign key constraint
    op.drop_constraint(
        "user_documents_user_id_fkey",
        "user_documents",
        type_="foreignkey",
    )

    # 2. Drop new index
    op.drop_index("ix_user_documents_user_uploaded", "user_documents")

    # 3. Rename columns back
    op.alter_column("users", "user_id", new_column_name="clerk_user_id")
    op.alter_column("user_documents", "user_id", new_column_name="clerk_user_id")

    # 4. Re-create old index
    op.create_index(
        "ix_user_documents_clerk_user_uploaded",
        "user_documents",
        ["clerk_user_id", "uploaded_at"],
    )

    # 5. Re-create old foreign key
    op.create_foreign_key(
        "user_documents_clerk_user_id_fkey",
        "user_documents",
        "users",
        ["clerk_user_id"],
        ["clerk_user_id"],
        ondelete="CASCADE",
    )
