"""
Database module: engine, sessions, ORM models, migrations (Alembic), repositories per entity.

- **Models** — `app.db.models` (e.g. `user.py`; add `document.py` when needed).
- **Repositories** — `app.db.repositories` (e.g. `users.py`; add `files.py` when needed).
- **Migrations** — `app.db/migrations/`; run from `backend/`: `uv run alembic -c alembic.ini upgrade head`
"""

from app.db.base import Base
from app.db.engine import close_db_engine, open_db_engine, to_async_dsn
from app.db.session import get_db_session

__all__ = [
    "Base",
    "close_db_engine",
    "get_db_session",
    "open_db_engine",
    "to_async_dsn",
]
