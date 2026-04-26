from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, cast

from app import store
from app.agents.graph import get_graph
from app.agents.nodes.answerer import on_token_var
from app.agents.state import GraphState
from app.api.documents import readiness_error_for_documents, resolve_chat_document_ids
from app.api.schemas import ChatRequest


def nd(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


async def chat_stream_ndjson(body: ChatRequest) -> AsyncIterator[bytes]:
    doc_ids = resolve_chat_document_ids(body)
    not_ready = readiness_error_for_documents(doc_ids)
    if not_ready is not None:
        yield nd({"type": "error", "message": not_ready})
        return

    primary = doc_ids[0]

    token_q: asyncio.Queue[str | None] = asyncio.Queue()

    async def on_token(text: str) -> None:
        await token_q.put(text)

    graph = get_graph()
    history: list[dict[str, str]] = [
        {"role": m.role, "content": m.content} for m in body.history
    ]
    initial: GraphState = {
        "document_id": primary,
        "document_ids": doc_ids,
        "query": body.message,
        "history": cast(Any, history),
        "attempts": 0,
        "trace": [],
    }

    async def run_graph() -> dict[str, Any]:
        token = on_token_var.set(on_token)
        try:
            return cast(dict[str, Any], await graph.ainvoke(initial))
        finally:
            on_token_var.reset(token)
            await token_q.put(None)

    graph_task = asyncio.create_task(run_graph())

    yield nd({"type": "stage", "name": "start", "detail": "running agent pipeline"})

    while True:
        token = await token_q.get()
        if token is None:
            break
        yield nd({"type": "content", "content": token})

    try:
        final_state = await graph_task
    except Exception as e:
        yield nd({"type": "error", "message": f"Agent pipeline failed: {e}"})
        return

    if final_state.get("final_route") == "reject" and final_state.get("answer"):
        yield nd({"type": "content", "content": final_state["answer"]})

    trace = {
        "document_id": primary,
        "document_ids": doc_ids,
        "query": body.message,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "steps": final_state.get("trace", []),
        "plan": final_state.get("plan"),
        "guardrail": final_state.get("guardrail"),
        "judge": final_state.get("judge"),
        "retrieved": [
            {
                "document_id": r.get("document_id"),
                "chunk_id": r.get("chunk_id"),
                "section_path": r.get("section_path"),
                "page": r.get("page"),
                "type": r.get("type"),
                "score": r.get("rerank_score", r.get("_score")),
                "preview": (r.get("display_text") or "")[:240],
                "bbox": r.get("bbox"),
                "page_size": r.get("page_size"),
            }
            for r in final_state.get("retrieved") or []
        ],
        "final_route": final_state.get("final_route", "answer"),
    }
    try:
        store.append_trace(primary, trace)
    except Exception:
        pass

    yield nd(
        {
            "type": "meta",
            "plan": final_state.get("plan"),
            "guardrail": final_state.get("guardrail"),
            "judge": final_state.get("judge"),
            "retrieved": trace["retrieved"],
        }
    )
