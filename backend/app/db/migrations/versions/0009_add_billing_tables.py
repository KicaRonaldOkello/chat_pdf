"""add billing tables (plans, subscriptions, usage_meter)

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision: str = "0008"
branch_labels = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("billing_period", sa.String(length=16), nullable=True),
        sa.Column("dodo_product_id", sa.String(length=128), nullable=True),
        sa.Column("price_cents", sa.BigInteger(), nullable=True),
        sa.Column("words_per_day", sa.BigInteger(), nullable=False),
        sa.Column("uploads_per_day", sa.Integer(), nullable=False),
        sa.Column("upload_bytes_per_day", sa.BigInteger(), nullable=False),
        sa.Column("files_in_scope", sa.Integer(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=False),
        sa.Column("dodo_subscription_id", sa.String(length=128), nullable=True),
        sa.Column("dodo_customer_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_method_id", sa.String(length=128), nullable=True),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("last_webhook_event", sa.String(length=64), nullable=True),
        sa.Column("last_webhook_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dodo_subscription_id"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    op.create_table(
        "usage_meter",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("ai_words", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("uploads", sa.Integer(), server_default="0", nullable=False),
        sa.Column("upload_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "usage_date", name="uq_usage_meter_user_date"),
    )
    op.create_index(
        "ix_usage_meter_user_date", "usage_meter", ["user_id", "usage_date"]
    )

    # Seed the plan catalog from the live pricing page (2026-08-19).
    # Limits: words/day, uploads/day, upload bytes/day, files in scope. -1 = unlimited.
    plans = sa.table(
        "plans",
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("billing_period", sa.String),
        sa.column("dodo_product_id", sa.String),
        sa.column("price_cents", sa.BigInteger),
        sa.column("words_per_day", sa.BigInteger),
        sa.column("uploads_per_day", sa.Integer),
        sa.column("upload_bytes_per_day", sa.BigInteger),
        sa.column("files_in_scope", sa.Integer),
    )
    op.bulk_insert(
        plans,
        [
            {
                "slug": "free",
                "name": "Free",
                "billing_period": None,
                "dodo_product_id": None,
                "price_cents": 0,
                "words_per_day": 2_000,
                "uploads_per_day": 5,
                "upload_bytes_per_day": 5 * 1024 * 1024,
                "files_in_scope": 2,
            },
            {
                "slug": "plus_monthly",
                "name": "Plus",
                "billing_period": "monthly",
                "dodo_product_id": None,
                "price_cents": 1_200,
                "words_per_day": 10_000,
                "uploads_per_day": 10,
                "upload_bytes_per_day": -1,
                "files_in_scope": 10,
            },
            {
                "slug": "plus_yearly",
                "name": "Plus",
                "billing_period": "yearly",
                "dodo_product_id": None,
                "price_cents": 11_520,
                "words_per_day": 10_000,
                "uploads_per_day": 10,
                "upload_bytes_per_day": -1,
                "files_in_scope": 10,
            },
            {
                "slug": "pro_monthly",
                "name": "Pro",
                "billing_period": "monthly",
                "dodo_product_id": None,
                "price_cents": 2_400,
                "words_per_day": -1,
                "uploads_per_day": -1,
                "upload_bytes_per_day": -1,
                "files_in_scope": -1,
            },
            {
                "slug": "pro_yearly",
                "name": "Pro",
                "billing_period": "yearly",
                "dodo_product_id": None,
                "price_cents": 23_040,
                "words_per_day": -1,
                "uploads_per_day": -1,
                "upload_bytes_per_day": -1,
                "files_in_scope": -1,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_usage_meter_user_date", table_name="usage_meter")
    op.drop_table("usage_meter")
    op.drop_index("ix_subscriptions_status", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_table("plans")
