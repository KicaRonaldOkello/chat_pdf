from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import ValidationError

from app import document_data
from app.agents.clients import openrouter_json
from app.agents.state import GraphState, RouterPlan
from app.config import ROUTER_MODEL, ROUTER_REQUEST_TIMEOUT
from app.processing.metadata import normalize_title

SYSTEM = (
    "You are a retrieval planner for a PDF question-answering system.\n\n"
    "One or more documents may be in scope. Each document has its own table of "
    "contents below. When route is structural or hybrid, you MUST use "
    "namespaced section IDs: `document_id:local_section_id` (both strings come "
    "from the TOC: use the `document_id` line for that document, and the `id` "
    "in brackets for the section). Never use a raw local section_id alone when "
    "more than one document is in scope.\n\n"
    "Given the documents' table of contents with per-section summaries,\n"
    "  optional per-document metadata (title, abstract, doc_type),\n"
    "  the user's current query and recent chat history,\n\n"
    "pick the best retrieval strategy:\n"
    "  * structural -- user refers to specific named sections/chapters/tables/"
    "figures (e.g. 'summarize the introduction', 'what does section 3 say').\n"
    "  * semantic   -- user asks about content; vector search works best.\n"
    "  * hybrid     -- both apply (e.g. 'compare the abstract and conclusion').\n\n"
    "When route is structural or hybrid, list the namespaced section_ids that "
    "should be pulled.  Always emit a concise `rewritten_query` that is "
    "self-contained for vector search.\n\n"
    "Respond with STRICT JSON only: "
    '{"route": "structural|semantic|hybrid", '
    '"section_ids": ["doc-uuid:sec-...", ...], '
    '"keywords": ["..."], '
    '"rewritten_query": "...", '
    '"rationale": "<=120 chars"}.'
)


def scope_document_ids(state: GraphState) -> list[str]:
    if state.get("document_ids"):
        return list(state["document_ids"])
    return [state["document_id"]]


def compact_toc(
    document_id: str, entries: list[dict[str, Any]], limit: int = 40
) -> str:
    rows: list[str] = []
    for e in entries[:limit]:
        summary = (e.get("summary") or "").strip()[:200]
        kws = ", ".join((e.get("keywords") or [])[:6])
        local_id = e.get("id", "")
        full_id = f"{document_id}:{local_id}" if local_id else document_id
        rows.append(
            f"- [{full_id}] {e.get('path', e.get('title'))}  "
            f"(pp. {e['page_range'][0]}-{e['page_range'][1]})"
            + (f"\n    summary: {summary}" if summary else "")
            + (f"\n    keywords: {kws}" if kws else "")
        )
    return "\n".join(rows)


def compact_meta(meta: dict[str, Any] | None) -> str:
    if not meta:
        return "(document meta unavailable)"
    bits = [
        f"doc_type: {meta.get('doc_type', '?')}",
        f"title: {meta.get('inferred_title', meta.get('filename', ''))}",
    ]
    abs_ = (meta.get("abstract") or "").strip()
    if abs_:
        bits.append(f"abstract: {abs_[:500]}")
    return "\n".join(bits)


async def render_user(state: GraphState, *, avoid_route: str | None = None) -> str:
    doc_ids = scope_document_ids(state)
    history = state.get("history") or []
    chat = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])
    retry_hint = (
        f"\n\nPREVIOUS ATTEMPT failed. Avoid route: {avoid_route}. "
        "Try a different strategy."
        if avoid_route
        else ""
    )
    parts: list[str] = []
    for did in doc_ids:
        entries = (await document_data.get_sections_index(did)) or []
        meta = await document_data.get_document_meta(did)
        st = await document_data.get_status(did)
        label = st.filename if st and st.filename else did
        parts.append(
            f"---\ndocument_id: {did}\n"
            f"file: {label}\n"
            f"Document metadata:\n{compact_meta(meta)}\n"
            f"Table of contents ({len(entries)} sections):\n"
            f"{compact_toc(did, entries)}\n"
        )
    return (
        f"{len(doc_ids)} document(s) in scope.\n\n"
        + "\n".join(parts)
        + f"\nRecent chat:\n{chat or '(none)'}\n\n"
        f"Current query: {state['query']}" + retry_hint
    )


async def fallback_heuristic(state: GraphState) -> RouterPlan:
    qnorm = state["query"].lower()
    qwords = {w for w in qnorm.replace("?", " ").split() if len(w) > 3}
    for did in scope_document_ids(state):
        entries = (await document_data.get_sections_index(did)) or []
        hits: list[str] = []
        for e in entries:
            nt = e.get("normalized_title") or normalize_title(e.get("title", ""))
            if not nt:
                continue
            if nt in qnorm or any(w == nt or w in nt for w in qwords):
                local = e.get("id")
                if local:
                    hits.append(f"{did}:{local}")
        if hits:
            return RouterPlan(
                route="structural",
                section_ids=hits[:4],
                rewritten_query=state["query"],
                rationale="fallback: title keyword match",
            )
    return RouterPlan(
        route="semantic",
        rewritten_query=state["query"],
        rationale="fallback: no title match",
    )


async def run(state: GraphState) -> dict[str, Any]:
    t0 = time.time()
    attempts = state.get("attempts", 0)
    avoid_route: str | None = None
    if attempts > 0:
        prev_route = (state.get("plan") or {}).get("route")
        avoid_route = prev_route

    async with httpx.AsyncClient() as client:
        parsed = await openrouter_json(
            client,
            model=ROUTER_MODEL,
            system=SYSTEM,
            user=await render_user(state, avoid_route=avoid_route),
            timeout=ROUTER_REQUEST_TIMEOUT,
        )

    plan = await fallback_heuristic(state)
    if isinstance(parsed, dict):
        try:
            plan = RouterPlan.model_validate(parsed)
        except ValidationError:
            pass

    if avoid_route and plan.route == avoid_route:
        plan = plan.model_copy(update={"route": "hybrid"})

    if plan.route == "structural" and not plan.section_ids:
        plan = plan.model_copy(update={"route": "semantic"})

    step = {
        "node": "router",
        "duration_ms": int((time.time() - t0) * 1000),
        "output": plan.model_dump(),
    }
    return {"plan": plan.model_dump(), "trace": [step]}
