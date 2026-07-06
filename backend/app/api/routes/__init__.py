"""Routes package — domain-specific APIRouter modules extracted from ``main.py``."""

from app.api.routes import auth, chat, documents, upload

__all__ = ["auth", "chat", "documents", "upload"]
