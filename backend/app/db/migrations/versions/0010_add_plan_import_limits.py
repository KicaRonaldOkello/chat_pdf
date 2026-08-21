"""add per-import upload limit to plans

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision: str = "0009"
branch_labels = None
depends_on: str | None = None

_FREE_IMPORT_BYTES = 5 * 1024 * 1024
_PLUS_IMPORT_BYTES = 100 * 1024 * 1024
_PRO_IMPORT_BYTES = 300 * 1024 * 1024


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column(
            "max_upload_bytes_per_import",
            sa.BigInteger(),
            nullable=False,
            server_default=str(_FREE_IMPORT_BYTES),
        ),
    )
    op.execute(
        sa.text(
            "UPDATE plans SET max_upload_bytes_per_import = :mb "
            "WHERE slug IN ('plus_monthly', 'plus_yearly')"
        ).bindparams(mb=_PLUS_IMPORT_BYTES)
    )
    op.execute(
        sa.text(
            "UPDATE plans SET max_upload_bytes_per_import = :mb "
            "WHERE slug IN ('pro_monthly', 'pro_yearly')"
        ).bindparams(mb=_PRO_IMPORT_BYTES)
    )


def downgrade() -> None:
    op.drop_column("plans", "max_upload_bytes_per_import")
