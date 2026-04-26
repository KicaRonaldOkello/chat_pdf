"""Read/write per-document JSON state (replaces on-disk `data/documents/...` files)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentState

Status = str


@dataclass
class DocumentStatus:
    status: Status
    stage: str
    progress: float
    filename: str
    error: str | None = None
    num_pages: int | None = None
    warnings: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> DocumentStatus:
        w = raw.get("warnings")
        if w is not None and not isinstance(w, list):
            w = None
        return DocumentStatus(
            status=raw["status"],
            stage=raw.get("stage", raw["status"]),
            progress=float(raw.get("progress", 0.0)),
            filename=raw.get("filename", ""),
            error=raw.get("error"),
            num_pages=raw.get("num_pages"),
            warnings=[str(x) for x in w] if w else None,
        )


def _row_to_status(row: DocumentState | None) -> DocumentStatus | None:
    if row is None:
        return None
    return DocumentStatus.from_dict(row.status_payload)


class DocumentStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_row(self, document_id: str) -> DocumentState | None:
        r = await self._session.execute(
            select(DocumentState).where(DocumentState.document_id == document_id)
        )
        return r.scalar_one_or_none()

    async def get_status(self, document_id: str) -> DocumentStatus | None:
        row = await self.get_row(document_id)
        return _row_to_status(row)

    async def set_status(self, document_id: str, status: DocumentStatus) -> None:
        row = await self.get_row(document_id)
        payload = status.to_dict()
        if row is None:
            self._session.add(
                DocumentState(
                    document_id=document_id,
                    status_payload=payload,
                    traces=[],
                )
            )
        else:
            row.status_payload = payload

    async def update_status(
        self, document_id: str, **kwargs: Any
    ) -> DocumentStatus:
        current = await self.get_status(document_id)
        if current is None:
            raise KeyError(f"Unknown document_id: {document_id}")
        merged = {**current.to_dict(), **kwargs}
        new = DocumentStatus(
            status=merged.get("status", current.status),
            stage=merged.get("stage", current.stage),
            progress=float(merged.get("progress", current.progress)),
            filename=merged.get("filename", current.filename),
            error=merged.get("error"),
            num_pages=merged.get("num_pages"),
            warnings=merged.get("warnings", current.warnings),
        )
        await self.set_status(document_id, new)
        return new

    async def save_tree(
        self, document_id: str, tree: dict[str, Any]
    ) -> None:
        row = await self.get_row(document_id)
        if row is None:
            raise KeyError(f"Unknown document_id: {document_id}")
        row.tree = tree

    async def get_tree(self, document_id: str) -> dict[str, Any] | None:
        row = await self.get_row(document_id)
        if row is None or row.tree is None:
            return None
        return row.tree if isinstance(row.tree, dict) else None

    async def save_sections_index(
        self, document_id: str, entries: list[dict[str, Any]]
    ) -> None:
        row = await self.get_row(document_id)
        if row is None:
            raise KeyError(f"Unknown document_id: {document_id}")
        row.sections_index = entries

    async def get_sections_index(
        self, document_id: str
    ) -> list[dict[str, Any]] | None:
        row = await self.get_row(document_id)
        if row is None or row.sections_index is None:
            return None
        return row.sections_index if isinstance(row.sections_index, list) else None

    async def save_document_meta(
        self, document_id: str, meta: dict[str, Any]
    ) -> None:
        row = await self.get_row(document_id)
        if row is None:
            raise KeyError(f"Unknown document_id: {document_id}")
        row.document_meta = meta

    async def get_document_meta(
        self, document_id: str
    ) -> dict[str, Any] | None:
        row = await self.get_row(document_id)
        if row is None or row.document_meta is None:
            return None
        return (
            row.document_meta if isinstance(row.document_meta, dict) else None
        )

    async def append_trace(
        self, document_id: str, trace: dict[str, Any]
    ) -> None:
        row = await self.get_row(document_id)
        if row is None:
            return
        cur = list(row.traces) if isinstance(row.traces, list) else []
        cur.insert(0, trace)
        row.traces = cur[:30]

    async def list_traces(
        self, document_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        row = await self.get_row(document_id)
        if row is None or not row.traces:
            return []
        out: list[dict[str, Any]] = []
        for t in row.traces[:limit]:
            if isinstance(t, dict):
                out.append(t)
        return out

    async def delete(self, document_id: str) -> None:
        row = await self.get_row(document_id)
        if row is not None:
            await self._session.delete(row)
