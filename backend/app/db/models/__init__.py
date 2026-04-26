"""
ORM models for Alembic and repositories.

Add new model modules here so `app.db.migrations` and `import app.db.models` register metadata.
"""

from app.db.models.user import User
from app.db.models.user_document import UserDocument

__all__ = ["User", "UserDocument"]
