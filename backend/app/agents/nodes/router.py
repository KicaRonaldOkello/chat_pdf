from __future__ import annotations

import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app import document_data
from app.agents.llm import create_llm
from app.agents.prompts import get_router_prompt
from app.agents.schemas import RouterPlan
from app.agents.state import GraphState
from app.config import ROUTER_MODEL
from app.processing.metadata import normalize_title

log = __import__("logging").getLogger(__name__)


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

    llm = create_llm(ROUTER_MODEL)
    structured = llm.with_structured_output(RouterPlan, method="json_mode")
    messages = [
        SystemMessage(content=get_router_prompt()),
        HumanMessage(content=await render_user(state, avoid_route=avoid_route)),
    ]

    plan = await fallback_heuristic(state)
    try:
        plan = await structured.ainvoke(messages)
    except Exception:
        log.debug("router structured output failed; using fallback", exc_info=True)

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
