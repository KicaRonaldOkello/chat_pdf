from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Engine

# `backend/` (package root) must be on path for `import app` when `uv run alembic` runs from `backend/`.
# env: backend/app/db/migrations/env.py -> .parents[3] == backend
_root = Path(__file__).resolve().parents[3]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_root / ".env", override=False)

import app.db.models  # noqa: F401, E402
from app.settings import settings  # noqa: E402

DATABASE_URL = settings.database_url
from app.db.base import Base  # noqa: E402


def _sync_database_url() -> str:
    """psycopg (sync) for Alembic CLI; same DSN as async app (`postgresql://...`)."""
    dsn = (DATABASE_URL or os.environ.get("DATABASE_URL") or "").strip()
    if not dsn:
        return "postgresql+psycopg://"
    if dsn.startswith("postgresql+psycopg_async://"):
        return dsn.replace("postgresql+psycopg_async://", "postgresql+psycopg://", 1)
    if dsn.startswith("postgresql+psycopg://"):
        return dsn
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    return dsn


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", _sync_database_url())
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = _sync_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable: Engine = create_engine(
        _sync_database_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
