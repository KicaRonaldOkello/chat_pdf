"""
Async access to per-document state (Postgres + storage backend for PDFs/images).
Replaces the former `app.store` filesystem under CHATPDF_DATA_DIR.
"""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from os import fdopen as _fdopen
from os import unlink as _unlink
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.document_state import (
    DocumentStateRepository,
    DocumentStatus,
)
from app.runtime import get_db_session_maker
from app.storage import get_storage

# Re-export for call sites
__all__ = [
    "DocumentStatus",
    "append_trace",
    "delete_document_artifacts",
    "document_db_session",
    "get_document_meta",
    "get_sections_index",
    "get_status",
    "get_tree",
    "list_traces",
    "pull_source_pdf_to_tempfile",
    "release_source_temp_path",
    "save_document_meta",
    "save_sections_index",
    "save_tree",
    "save_upload_and_record",
    "set_status",
    "update_status",
]


@asynccontextmanager
async def document_db_session() -> AsyncIterator[
    tuple[AsyncSession, DocumentStateRepository]
]:
    sm = get_db_session_maker()
    if sm is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with sm() as session:
        yield session, DocumentStateRepository(session)


async def get_status(document_id: str) -> DocumentStatus | None:
    sm = get_db_session_maker()
    if sm is None:
        return None
    async with sm() as session:
        repo = DocumentStateRepository(session)
        return await repo.get_status(document_id)


async def set_status(document_id: str, st: DocumentStatus) -> None:
    async with document_db_session() as (session, repo):
        await repo.set_status(document_id, st)
        await session.commit()


async def update_status(
    document_id: str, **kwargs: Any
) -> DocumentStatus:
    async with document_db_session() as (session, repo):
        new = await repo.update_status(document_id, **kwargs)
        await session.commit()
        return new


async def save_tree(document_id: str, tree: dict[str, Any]) -> None:
    async with document_db_session() as (session, repo):
        await repo.save_tree(document_id, tree)
        await session.commit()


async def get_tree(document_id: str) -> dict[str, Any] | None:
    sm = get_db_session_maker()
    if sm is None:
        return None
    async with sm() as session:
        repo = DocumentStateRepository(session)
        return await repo.get_tree(document_id)


async def save_sections_index(
    document_id: str, entries: list[dict[str, Any]]
) -> None:
    async with document_db_session() as (session, repo):
        await repo.save_sections_index(document_id, entries)
        await session.commit()


async def get_sections_index(
    document_id: str,
) -> list[dict[str, Any]] | None:
    sm = get_db_session_maker()
    if sm is None:
        return None
    async with sm() as session:
        repo = DocumentStateRepository(session)
        return await repo.get_sections_index(document_id)


async def save_document_meta(
    document_id: str, meta: dict[str, Any]
) -> None:
    async with document_db_session() as (session, repo):
        await repo.save_document_meta(document_id, meta)
        await session.commit()


async def get_document_meta(
    document_id: str,
) -> dict[str, Any] | None:
    sm = get_db_session_maker()
    if sm is None:
        return None
    async with sm() as session:
        repo = DocumentStateRepository(session)
        return await repo.get_document_meta(document_id)


async def append_trace(
    document_id: str, trace: dict[str, Any]
) -> None:
    async with document_db_session() as (session, repo):
        await repo.append_trace(document_id, trace)
        await session.commit()


async def list_traces(
    document_id: str, limit: int = 20
) -> list[dict[str, Any]]:
    sm = get_db_session_maker()
    if sm is None:
        return []
    async with sm() as session:
        repo = DocumentStateRepository(session)
        return await repo.list_traces(document_id, limit=limit)


async def delete_document_artifacts(document_id: str) -> None:
    async with document_db_session() as (session, repo):
        await repo.delete(document_id)
        await session.commit()


def pull_source_pdf_to_tempfile(document_id: str) -> Path:
    """Sync: download source PDF to temp; used from asyncio.to_thread in the pipeline."""
    data = get_storage().get_source_pdf_bytes(document_id)
    fd, name = tempfile.mkstemp(suffix=".pdf", prefix="chatpdf-src-")
    try:
        with _fdopen(fd, "wb", closefd=True) as f:
            f.write(data)
    except Exception:
        try:
            _unlink(name)
        except OSError:
            pass
        raise
    return Path(name)


def release_source_temp_path(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


async def save_upload_and_record(
    data: bytes, filename: str
) -> str:
    document_id = str(uuid.uuid4())
    get_storage().put_source_pdf_bytes(document_id, data)
    st = DocumentStatus(
        status="queued",
        stage="queued",
        progress=0.0,
        filename=filename,
    )
    await set_status(document_id, st)
    return document_id
