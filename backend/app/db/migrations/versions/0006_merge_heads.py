"""merge heads 0005 and bfb9db12e95c

Revision ID: 0006
Revises: 0005, bfb9db12e95c
Create Date: 2026-07-08
"""

from collections.abc import Sequence

revision: str = "0006"
down_revision: str | tuple[str, ...] | None = ("0005", "bfb9db12e95c")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
