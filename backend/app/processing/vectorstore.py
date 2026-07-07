"""Vector storage backed by PostgreSQL pgvector.

Replaces the former Qdrant-based implementation.  The public API is
unchanged — search, upsert, fetch_by_section, and delete_doc all keep
the same signatures and return the same hit-dict shapes.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.processing.chunking import Chunk
from app.runtime import get_db_session_maker


def _session() -> Any:
    sm = get_db_session_maker()
    if sm is None:
        raise RuntimeError("DATABASE_URL is not configured")
    return sm()


def _row_to_hit(row: Any, score: float = 1.0) -> dict[str, Any]:
    """Map a document_chunks row to the same hit-dict shape that Qdrant
    payloads used to provide.  Downstream code expects this shape."""
    hit: dict[str, Any] = {
        "chunk_id": row.chunk_id,
        "document_id": row.document_id,
        "element_ids": row.element_ids or [],
        "type": row.type,
        "section_path": row.section_path or "(root)",
        "page": row.page or 1,
        "display_text": row.display_text or "",
        "_score": float(score),
    }
    if row.bbox is not None:
        hit["bbox"] = row.bbox
    if row.page_size is not None:
        hit["page_size"] = row.page_size
    # Merge extra JSONB fields flattened, same as Qdrant
    extra = row.extra or {}
    if isinstance(extra, dict):
        for k, v in extra.items():
            if k not in hit:
                hit[k] = v
    return hit


# ── Public API (same signatures as before) ──────────────────────────────


async def ensure_collection() -> None:
    """No-op — schema is managed by Alembic migrations."""
    return


def _chunk_params(chunk: Chunk, vector: list[float]) -> dict[str, Any]:
    payload = chunk.payload()
    extra_fields = {
        k: v
        for k, v in payload.items()
        if k
        not in (
            "chunk_id",
            "document_id",
            "type",
            "section_path",
            "page",
            "display_text",
            "element_ids",
            "bbox",
            "page_size",
        )
    }
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "embedding": vector,
        "type": chunk.type,
        "section_path": chunk.section_path,
        "page": chunk.page,
        "display_text": chunk.display_text,
        "element_ids": json.dumps(chunk.element_ids),
        "bbox": json.dumps(chunk.bbox) if chunk.bbox else None,
        "page_size": json.dumps(chunk.page_size) if chunk.page_size else None,
        "extra": json.dumps(extra_fields),
    }


async def upsert_chunks(
    chunks: list[Chunk],
    vectors: list[list[float]],
    *,
    session: Any = None,
) -> None:
    if not chunks:
        return

    async def _do(sess: Any) -> None:
        params = [_chunk_params(c, v) for c, v in zip(chunks, vectors, strict=False)]
        await sess.execute(upsert_sql(), params)

    if session is not None:
        await _do(session)
    else:
        async with _session() as sess:
            await _do(sess)
            await sess.commit()


async def search(
    document_ids: str | list[str], vector: list[float], top_k: int
) -> list[dict[str, Any]]:
    ids = [document_ids] if isinstance(document_ids, str) else list(document_ids)
    if not ids:
        return []
    async with _session() as session:
        result = await session.execute(
            _SEARCH_SQL,
            {"doc_ids": ids, "vec": vector, "k": top_k},
        )
        return [_row_to_hit(row, score=row._score) for row in result]


async def fetch_by_section(
    document_id: str, section_paths: list[str], max_chunks: int = 40
) -> list[dict[str, Any]]:
    if not section_paths:
        return []
    async with _session() as session:
        result = await session.execute(
            _FETCH_BY_SECTION_SQL,
            {"doc_id": document_id, "paths": section_paths, "limit": max_chunks},
        )
        return [_row_to_hit(row) for row in result]


async def fetch_by_section_multi(
    docs_to_paths: dict[str, list[str]], max_chunks: int = 40
) -> list[dict[str, Any]]:
    nonempty = {d: list(dict.fromkeys(p)) for d, p in docs_to_paths.items() if p}
    if not nonempty:
        return []
    if len(nonempty) == 1:
        d, pth = next(iter(nonempty.items()))
        return await fetch_by_section(d, pth, max_chunks)

    n = len(nonempty)
    per = max(8, max_chunks // n)
    out: list[dict[str, Any]] = []
    for d, pth in nonempty.items():
        out.extend(await fetch_by_section(d, pth, per))

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for h in out:
        cid = h.get("chunk_id", "")
        if cid in seen:
            continue
        seen.add(cid)
        unique.append(h)
    unique.sort(
        key=lambda h: (
            str(h.get("document_id", "")),
            h.get("page", 0),
            str(h.get("chunk_id", "")),
        )
    )
    return unique[:max_chunks]


async def delete_doc(
    document_id: str, *, session: Any = None
) -> None:
    if session is not None:
        await session.execute(_DELETE_SQL, {"doc_id": document_id})
    else:
        async with _session() as sess:
            await sess.execute(_DELETE_SQL, {"doc_id": document_id})
            await sess.commit()


# ── SQL ─────────────────────────────────────────────────────────────────


def upsert_sql() -> Any:
    return text(
        """INSERT INTO document_chunks
            (chunk_id, document_id, embedding, type, section_path, page,
             display_text, element_ids, bbox, page_size, extra)
        VALUES
            (:chunk_id, :document_id, cast(:embedding as vector), :type, :section_path, :page,
             :display_text, :element_ids, :bbox, :page_size, :extra)
        ON CONFLICT (chunk_id) DO UPDATE SET
            document_id = EXCLUDED.document_id,
            embedding = EXCLUDED.embedding,
            type = EXCLUDED.type,
            section_path = EXCLUDED.section_path,
            page = EXCLUDED.page,
            display_text = EXCLUDED.display_text,
            element_ids = EXCLUDED.element_ids,
            bbox = EXCLUDED.bbox,
            page_size = EXCLUDED.page_size,
            extra = EXCLUDED.extra"""
    )


_SEARCH_SQL = text(
    """SELECT *, 1 - (embedding <=> cast(:vec as vector)) AS _score
    FROM document_chunks
    WHERE document_id = ANY(:doc_ids)
    ORDER BY embedding <=> cast(:vec as vector)
    LIMIT :k"""
)

_FETCH_BY_SECTION_SQL = text(
    """SELECT *, 1.0 AS _score
    FROM document_chunks
    WHERE document_id = :doc_id AND section_path = ANY(:paths)
    ORDER BY page, chunk_id
    LIMIT :limit"""
)

_DELETE_SQL = text(
    "DELETE FROM document_chunks WHERE document_id = :doc_id"
)
