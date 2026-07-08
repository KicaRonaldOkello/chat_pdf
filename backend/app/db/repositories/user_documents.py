"""User-scoped document rows (upload history / recents)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserDocument


@dataclass(frozen=True)
class UserDocumentRow:
    document_id: str
    filename: str
    file_size_bytes: int | None
    uploaded_at: datetime


class UserDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record_upload(
        self,
        user_id: str,
        document_id: str,
        filename: str,
        file_size_bytes: int,
    ) -> None:
        self._session.add(
            UserDocument(
                user_id=user_id,
                document_id=document_id,
                filename=filename,
                file_size_bytes=file_size_bytes,
            )
        )

    async def list_for_user(self, user_id: str, limit: int) -> list[UserDocumentRow]:
        stmt = (
            select(
                UserDocument.document_id,
                UserDocument.filename,
                UserDocument.file_size_bytes,
                UserDocument.uploaded_at,
            )
            .where(UserDocument.user_id == user_id)
            .order_by(desc(UserDocument.uploaded_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.all()
        return [
            UserDocumentRow(
                document_id=r[0], filename=r[1], file_size_bytes=r[2], uploaded_at=r[3]
            )
            for r in rows
        ]

    async def list_recent(self, user_id: str, limit: int = 3) -> list[UserDocumentRow]:
        return await self.list_for_user(user_id, limit)

    async def delete_by_document_id(self, document_id: str) -> None:
        await self._session.execute(
            delete(UserDocument).where(UserDocument.document_id == document_id)
        )

    async def is_owner(self, user_id: str, document_id: str) -> bool:
        stmt = (
            select(UserDocument.document_id)
            .where(
                UserDocument.user_id == user_id,
                UserDocument.document_id == document_id,
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.first() is not None
