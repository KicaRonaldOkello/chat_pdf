from __future__ import annotations

import asyncio
import time
from typing import Any

from app import document_data
from app.agents.state import GraphState
from app.config import (
    MAX_CONTEXT_CHARS,
    RERANK_ENABLED,
    RERANK_RECALL_LIMIT,
    RETRIEVAL_TOP_K,
)
from app.processing import embeddings, rerank, vectorstore
from app.storage import get_storage


def scope_document_ids(state: GraphState) -> list[str]:
    if state.get("document_ids"):
        return list(state["document_ids"])
    return [state["document_id"]]


async def display_filename(doc_id: str) -> str:
    s = await document_data.get_status(doc_id)
    if s and (s.filename or "").strip():
        return s.filename.strip()
    return doc_id


def recall_vector_limit() -> int:
    return RERANK_RECALL_LIMIT if RERANK_ENABLED else RETRIEVAL_TOP_K


def structural_max_chunks() -> int:
    return min(64, RERANK_RECALL_LIMIT) if RERANK_ENABLED else 30


async def structural_paths_by_document(
    state: GraphState, plan: dict[str, Any]
) -> dict[str, list[str]]:
    doc_ids = scope_document_ids(state)
    out: dict[str, list[str]] = {d: [] for d in doc_ids}
    for sid in plan.get("section_ids", []):
        s = str(sid)
        if ":" in s:
            head, tail = s.split(":", 1)
            if head in out:
                entries = (await document_data.get_sections_index(head)) or []
                by_id = {e["id"]: e for e in entries}
                e = by_id.get(tail)
                if e and e.get("path"):
                    out[head].append(e["path"])
                    continue
        for d in doc_ids:
            entries = (await document_data.get_sections_index(d)) or []
            by_id = {e["id"]: e for e in entries}
            e = by_id.get(s)
            if e and e.get("path"):
                out[d].append(e["path"])
    return {d: list(dict.fromkeys(pth)) for d, pth in out.items() if pth}


async def structural(state: GraphState, plan: dict[str, Any]) -> list[dict[str, Any]]:
    cap = structural_max_chunks()
    paths_by_doc = await structural_paths_by_document(state, plan)
    if not paths_by_doc:
        return []
    if len(paths_by_doc) == 1:
        d, paths = next(iter(paths_by_doc.items()))
        hits = await vectorstore.fetch_by_section(d, paths, max_chunks=cap)
    else:
        hits = await vectorstore.fetch_by_section_multi(paths_by_doc, max_chunks=cap)
    hits.sort(
        key=lambda h: (
            str(h.get("document_id", "")),
            h.get("page", 0),
            h.get("chunk_id", ""),
        )
    )
    return hits


async def semantic(state: GraphState, plan: dict[str, Any]) -> list[dict[str, Any]]:
    query = plan.get("rewritten_query") or state["query"]
    vec = await embeddings.embed_query(query)
    if not vec:
        return []
    return await vectorstore.search(
        scope_document_ids(state), vec, recall_vector_limit()
    )


def dedupe(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for h in hits:
        key = h.get("chunk_id") or (
            f"{h.get('document_id')}:{h.get('section_path')}::{h.get('page')}"
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


async def hybrid(state: GraphState, plan: dict[str, Any]) -> list[dict[str, Any]]:
    struct_hits = await structural(state, plan)
    sem_hits = await semantic(state, plan)
    merged = dedupe(struct_hits + sem_hits)
    cap = recall_vector_limit()
    return merged[: max(cap, len(struct_hits) + 4)]


async def format_context(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return ""
    key_order: list[tuple[str, str]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for h in hits:
        did = str(h.get("document_id", ""))
        sp = h.get("section_path") or "(root)"
        k = (did, sp)
        if k not in grouped:
            grouped[k] = []
            key_order.append(k)
        grouped[k].append(h)

    context_chars = 0
    blocks: list[str] = []
    for did, sp in key_order:
        rows = grouped[(did, sp)]
        rows.sort(
            key=lambda r: (
                r.get("page", 0),
                -float(r.get("rerank_score", r.get("_score", 0)) or 0),
            )
        )
        label = await display_filename(did)
        head = f"## {label} — {sp}"
        blocks.append(head)
        for r in rows:
            header = f"[p.{r.get('page', '?')}]"
            display = r.get("display_text", "")

            # Hydrate truncated tables from disk storage when it fits
            if r.get("table_truncated") and r.get("table_path"):
                try:
                    full_md = await asyncio.to_thread(
                        get_storage().get_table_markdown,
                        did,
                        str(r["table_path"]),
                    )
                    # Only include full table if it won't blow the context budget
                    if context_chars + len(full_md) < MAX_CONTEXT_CHARS:
                        display = full_md
                    # Otherwise keep the preview (already in display_text)
                except FileNotFoundError:
                    pass  # keep preview from display_text

            block = f"{header}\n{display}"
            blocks.append(block)
            context_chars += len(block)
    return "\n\n".join(blocks)


async def run(state: GraphState) -> dict[str, Any]:
    t0 = time.time()
    plan = state.get("plan") or {}
    route = plan.get("route", "semantic")

    if route == "structural":
        hits = await structural(state, plan)
        if not hits:
            hits = await semantic(state, plan)
            route = "semantic-fallback"
    elif route == "hybrid":
        hits = await hybrid(state, plan)
    else:
        hits = await semantic(state, plan)

    hits = dedupe(hits)
    doc_ids = scope_document_ids(state)
    rerank_info: dict[str, Any] | None
    if RERANK_ENABLED:
        hits = hits[:RERANK_RECALL_LIMIT]
        hits, rerank_info = await rerank.rerank_hits(
            state["query"],
            hits,
            RETRIEVAL_TOP_K,
            len(doc_ids),
        )
    else:
        hits = hits[:RETRIEVAL_TOP_K]
        rerank_info = None

    context = await format_context(hits)
    step: dict[str, Any] = {
        "node": "retrieve",
        "duration_ms": int((time.time() - t0) * 1000),
        "output": {
            "route_taken": route,
            "num_hits": len(hits),
            "section_paths": sorted({h.get("section_path", "") for h in hits}),
        },
    }
    if rerank_info is not None:
        step["output"]["rerank"] = rerank_info
    return {"retrieved": hits, "context": context, "trace": [step]}
