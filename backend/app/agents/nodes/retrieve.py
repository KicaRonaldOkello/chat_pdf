from __future__ import annotations

import asyncio
import time
from typing import Any

from app import document_data
from app.agents.journey import JourneyLogger
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
    """Run semantic search for ALL query variants from the router plan."""
    doc_ids = scope_document_ids(state)
    query = plan.get("rewritten_query") or state.get("query", "")
    variants: list[str] = list(plan.get("query_variants") or [])

    # Build query list: router variants first, then fall back to
    # rewritten_query + gap_query from state if we're in a retry.
    queries: list[str] = []
    seen_q: set[str] = set()
    for q in variants:
        if q and q not in seen_q:
            queries.append(q)
            seen_q.add(q)
    if not queries:
        queries.append(query)

    # Append key_entities as additional search terms — the router
    # extracts these from the query and they anchor entity-specific
    # retrieval (e.g. "lending rate", "Central Bank Rate").
    entities = plan.get("key_entities") or []
    for e in entities[:5]:
        if e and e not in seen_q:
            queries.append(e)
            seen_q.add(e)

    # If we're in a retry round, prepend the gap_query
    gap = state.get("gap_query", "")
    if gap and gap not in seen_q:
        queries.insert(0, gap)

    queries = queries[:8]  # cap
    limit_per_query = max(3, recall_vector_limit() // max(1, len(queries)))

    all_hits: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for q in queries:
        vec = await embeddings.embed_query(q)
        if not vec:
            continue
        hits = await vectorstore.search(doc_ids, vec, limit_per_query)
        for h in hits:
            cid = h.get("chunk_id", "")
            if cid not in seen_ids:
                seen_ids.add(cid)
                all_hits.append(h)

    # Post-retrieval: if the router specified target sections, boost
    # chunks from those sections to the front of the result list.
    target_sections: list[str] = list(plan.get("target_sections") or [])
    if target_sections and all_hits:
        def _section_boost(hit: dict[str, Any]) -> float:
            sp = str(hit.get("section_path", "")).lower()
            for ts in target_sections:
                if ts.lower() in sp:
                    return 1.0  # full boost
            return 0.0

        all_hits.sort(key=lambda h: -_section_boost(h))

    return all_hits


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


async def format_context(
    hits: list[dict[str, Any]], *, doc_ids: list[str] | None = None
) -> str:
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

    # Collect pages that already have table chunks — we'll try to hydrate
    # adjacent pages too.
    table_pages: set[int] = {r.get("page", 0) for r in hits if r.get("type") == "table"}

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

    # ── Adjacent table hydration ───────────────────────────────────────
    # When a table chunk is retrieved, also pull tables from adjacent pages
    # (the table often spans several pages, e.g. pages 34-37).
    if table_pages:
        adjacent_pages: set[int] = set()
        for p in table_pages:
            adjacent_pages.add(p + 1)
            adjacent_pages.add(p + 2)
        adjacent_pages -= table_pages  # don't duplicate pages we already have

        for adj_page in sorted(adjacent_pages):
            if context_chars > MAX_CONTEXT_CHARS:
                break
            # Try to load a table markdown file for this adjacent page
            for did in (doc_ids or []):
                try:
                    storage = get_storage()
                    key = f"tables/table_{adj_page}.md"
                    adj_md = await asyncio.to_thread(
                        storage.get_table_markdown, did, key
                    )
                    if adj_md:
                        # Include up to 2000 chars of the adjacent table
                        snippet = adj_md[:2000]
                        label = await display_filename(did)
                        blocks.append(
                            f"## {label} — (adjacent table p.{adj_page})\n"
                            f"[p.{adj_page}]\n{snippet}"
                        )
                        context_chars += len(snippet) + 100
                        break
                except (FileNotFoundError, Exception):
                    pass

    return "\n\n".join(blocks)


async def run(state: GraphState) -> dict[str, Any]:
    logger = JourneyLogger("retrieve")
    logger.log_start()
    
    plan = state.get("plan") or {}
    route = plan.get("route", "semantic")
    logger.log_info(f"Route: {route}")

    if route == "structural":
        hits = await structural(state, plan)
        # Structural often matches section headings that have no body text
        # (e.g. "Exchange Rates [Source: BOU]" with 0 elements).  When we
        # get too few chunks, augment with semantic search.
        if len(hits) < 3:
            logger.log_info(
                f"Structural returned only {len(hits)} chunk(s); augmenting with semantic"
            )
            sem_hits = await semantic(state, plan)
            hits = dedupe(hits + sem_hits)
            route = "semantic-fallback"
        elif not hits:
            logger.log_info("Structural returned no hits, falling back to semantic")
            hits = await semantic(state, plan)
            route = "semantic-fallback"
    elif route == "hybrid":
        hits = await hybrid(state, plan)
    else:
        hits = await semantic(state, plan)

    hits = dedupe(hits)
    logger.log_info(f"After dedupe: {len(hits)} chunks")
    
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
        logger.log_info(f"After rerank: {len(hits)} chunks")
    else:
        hits = hits[:RETRIEVAL_TOP_K]
        rerank_info = None
        logger.log_info(f"Top-k: {len(hits)} chunks")

    retrieval_attempts = state.get("retrieval_attempts", 0) + 1
    context = await format_context(hits, doc_ids=doc_ids)
    
    journey_data = logger.log_complete({
        "route_taken": route,
        "num_hits": len(hits),
        "retrieval_attempt": retrieval_attempts,
        "rerank_enabled": RERANK_ENABLED,
    })
    
    step: dict[str, Any] = {
        "node": "retrieve",
        "duration_ms": journey_data["duration_ms"],
        "output": {
            "route_taken": route,
            "num_hits": len(hits),
            "retrieval_attempt": retrieval_attempts,
            "section_paths": sorted({h.get("section_path", "") for h in hits}),
        },
    }
    if rerank_info is not None:
        step["output"]["rerank"] = rerank_info
    return {
        "retrieved": hits,
        "context": context,
        "retrieval_attempts": retrieval_attempts,
        "trace": [step],
        "journey": [journey_data],
    }
