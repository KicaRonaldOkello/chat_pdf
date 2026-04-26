from __future__ import annotations

import asyncio
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.config import (
    EMBEDDING_DIM,
    QDRANT_CLIENT_TIMEOUT,
    QDRANT_COLLECTION,
    QDRANT_POINT_NAMESPACE,
    QDRANT_URL,
)
from app.processing.chunking import Chunk

NAMESPACE = uuid.UUID(QDRANT_POINT_NAMESPACE)


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(NAMESPACE, chunk_id))


def client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, timeout=QDRANT_CLIENT_TIMEOUT)


def ensure_collection_sync() -> None:
    c = client()
    existing = {col.name for col in c.get_collections().collections}
    if QDRANT_COLLECTION not in existing:
        c.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=qm.VectorParams(
                size=EMBEDDING_DIM, distance=qm.Distance.COSINE
            ),
        )
    for field in ("document_id", "section_path"):
        try:
            c.create_payload_index(
                collection_name=QDRANT_COLLECTION,
                field_name=field,
                field_schema=qm.PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass


async def ensure_collection() -> None:
    await asyncio.to_thread(ensure_collection_sync)


def upsert_sync(chunks: list[Chunk], vectors: list[list[float]]) -> None:
    if not chunks:
        return
    points: list[qm.PointStruct] = []
    for ch, vec in zip(chunks, vectors, strict=False):
        points.append(
            qm.PointStruct(id=point_id(ch.chunk_id), vector=vec, payload=ch.payload())
        )
    client().upsert(collection_name=QDRANT_COLLECTION, points=points, wait=True)


async def upsert_chunks(chunks: list[Chunk], vectors: list[list[float]]) -> None:
    await asyncio.to_thread(upsert_sync, chunks, vectors)


def normalize_document_ids(document_ids: str | list[str]) -> list[str]:
    if isinstance(document_ids, str):
        return [document_ids]
    return list(document_ids)


def document_id_match_condition(document_ids: list[str]) -> qm.FieldCondition:
    if len(document_ids) == 1:
        return qm.FieldCondition(
            key="document_id", match=qm.MatchValue(value=document_ids[0])
        )
    return qm.FieldCondition(
        key="document_id", match=qm.MatchAny(any=list(document_ids))
    )


def search_sync(
    document_ids: str | list[str], vector: list[float], top_k: int
) -> list[dict[str, Any]]:
    ids = normalize_document_ids(document_ids)
    if not ids:
        return []
    flt = qm.Filter(must=[document_id_match_condition(ids)])
    res = client().query_points(
        collection_name=QDRANT_COLLECTION,
        query=vector,
        query_filter=flt,
        limit=top_k,
        with_payload=True,
    )
    out: list[dict[str, Any]] = []
    for p in res.points:
        payload = dict(p.payload or {})
        payload["_score"] = float(p.score) if p.score is not None else 0.0
        out.append(payload)
    return out


async def search(
    document_ids: str | list[str], vector: list[float], top_k: int
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(search_sync, document_ids, vector, top_k)


def fetch_by_section_sync(
    document_id: str, section_paths: list[str], max_chunks: int = 40
) -> list[dict[str, Any]]:
    if not section_paths:
        return []
    flt = qm.Filter(
        must=[
            document_id_match_condition([document_id]),
            qm.FieldCondition(
                key="section_path", match=qm.MatchAny(any=list(section_paths))
            ),
        ]
    )
    out: list[dict[str, Any]] = []
    offset = None
    remaining = max_chunks
    while remaining > 0:
        batch_size = min(remaining, 128)
        pts, offset = client().scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=flt,
            limit=batch_size,
            with_payload=True,
            with_vectors=False,
            offset=offset,
        )
        for p in pts:
            payload = dict(p.payload or {})
            payload["_score"] = 1.0
            out.append(payload)
        remaining -= len(pts)
        if offset is None:
            break
    return out


async def fetch_by_section(
    document_id: str, section_paths: list[str], max_chunks: int = 40
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        fetch_by_section_sync, document_id, section_paths, max_chunks
    )


def fetch_by_section_multi_sync(
    docs_to_paths: dict[str, list[str]], max_chunks: int = 40
) -> list[dict[str, Any]]:
    nonempty: dict[str, list[str]] = {
        d: list(dict.fromkeys(p))
        for d, p in docs_to_paths.items()
        if p
    }
    if not nonempty:
        return []
    if len(nonempty) == 1:
        d, pth = next(iter(nonempty.items()))
        return fetch_by_section_sync(d, pth, max_chunks)
    n = len(nonempty)
    per = max(8, max_chunks // n)
    out: list[dict[str, Any]] = []
    for d, pth in nonempty.items():
        out.extend(fetch_by_section_sync(d, pth, per))
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


async def fetch_by_section_multi(
    docs_to_paths: dict[str, list[str]], max_chunks: int = 40
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        fetch_by_section_multi_sync, docs_to_paths, max_chunks
    )


def delete_doc_sync(document_id: str) -> None:
    flt = qm.Filter(must=[document_id_match_condition([document_id])])
    client().delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=qm.FilterSelector(filter=flt),
        wait=True,
    )


async def delete_doc(document_id: str) -> None:
    await asyncio.to_thread(delete_doc_sync, document_id)
