from __future__ import annotations

import asyncio
import json
import logging
import traceback
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, cast

from app import document_data
from app.agents.graph import get_graph
from app.agents.nodes.answerer import on_token_var
from app.agents.state import GraphState
from app.api.documents import readiness_error_for_documents, resolve_chat_document_ids
from app.api.schemas import ChatRequest

log = logging.getLogger(__name__)


def nd(obj: dict[str, Any]) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


async def chat_stream_ndjson(body: ChatRequest) -> AsyncIterator[bytes]:
    doc_ids = resolve_chat_document_ids(body)
    not_ready = await readiness_error_for_documents(doc_ids)
    if not_ready is not None:
        yield nd({"type": "error", "message": not_ready})
        return

    primary = doc_ids[0]

    # Token queue is kept for the answerer to push into (avoids backpressure)
    # but we no longer stream tokens progressively.  Instead we wait for the
    # graph to finish and send the final answer — this prevents the user from
    # seeing intermediate answers that the judge later retries.
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
        "journey": [],
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

    # Drain the token queue in the background so the answerer doesn't block,
    # but don't yield content — we only send the final answer.
    async def _drain() -> None:
        while True:
            t = await token_q.get()
            if t is None:
                return

    drain_task = asyncio.create_task(_drain())

    _GRAPH_TIMEOUT = 300  # seconds
    try:
        final_state = await asyncio.wait_for(graph_task, timeout=_GRAPH_TIMEOUT)
    except TimeoutError:
        log.error("graph timed out after %.0fs", _GRAPH_TIMEOUT)
        drain_task.cancel()
        yield nd({"type": "error", "message": "Request timed out"})
        return
    except Exception as e:
        log.exception("agent pipeline failed for query=%r", body.message[:100])
        error_detail = traceback.format_exc()[-500:]
        drain_task.cancel()
        yield nd({
            "type": "error",
            "message": f"Agent pipeline failed: {type(e).__name__}: {e}",
            "detail": error_detail,
        })
        return

    drain_task.cancel()

    if (final_state.get("final_route") == "reject" and final_state.get("answer")) or final_state.get("answer"):
        yield nd({"type": "content", "content": final_state["answer"]})

    # Stream journey events (batched as requested)
    journey_events = final_state.get("journey", [])
    for event in journey_events:
        yield nd({"type": "journey", **event})

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
        await document_data.append_trace(primary, trace)
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
