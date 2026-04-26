"""Repository factories for FastAPI `Depends`. Add one per model repository."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.user_documents import UserDocumentRepository
from app.db.repositories.users import UserRepository
from app.db.session import get_db_session


def get_user_repository(
    session: AsyncSession = Depends(get_db_session),
) -> UserRepository:
    return UserRepository(session)


def get_user_document_repository(
    session: AsyncSession = Depends(get_db_session),
) -> UserDocumentRepository:
    return UserDocumentRepository(session)
