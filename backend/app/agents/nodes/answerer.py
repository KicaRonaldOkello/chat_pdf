from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.llm import create_llm
from app.agents.prompts import get_answerer_system_prompt
from app.agents.state import GraphState
from app.config import ANSWERER_MODEL

TokenCallback = Callable[[str], Awaitable[None]]
on_token_var: ContextVar[TokenCallback | None] = ContextVar("on_token", default=None)

log = __import__("logging").getLogger(__name__)


def _build_langchain_messages(state: GraphState) -> list:
    doc_ids = state.get("document_ids")
    if doc_ids and len(doc_ids) > 1:
        system = (
            f"The user has {len(doc_ids)} PDF(s) in this chat. Use the retrieved "
            f"excerpts from any or all of them to answer, including cross-document "
            f"comparisons and common themes. "
        ) + get_answerer_system_prompt(multi_doc=True)
    else:
        system = get_answerer_system_prompt(multi_doc=False)
    system += (
        "\n\n--- retrieved context ---\n"
        f"{state.get('context') or '(no context retrieved)'}\n"
        "--- end context ---"
    )

    msgs: list = [SystemMessage(content=system)]
    for m in state.get("history") or []:
        role = m["role"]
        if role == "assistant":
            msgs.append(AIMessage(content=m["content"]))
        else:
            msgs.append(HumanMessage(content=m["content"]))
    msgs.append(HumanMessage(content=state["query"]))
    return msgs


async def run(state: GraphState) -> dict[str, Any]:
    t0 = time.time()
    on_token = on_token_var.get()

    llm = create_llm(
        ANSWERER_MODEL,
        temperature=0.0,
        extra_body={"reasoning": {"effort": "minimal", "exclude": True}},
    )
    messages = _build_langchain_messages(state)

    chunks: list[str] = []
    try:
        async for chunk in llm.astream(messages):
            raw = chunk.content if hasattr(chunk, "content") else None
            if not raw:
                continue
            # Normalise content: streaming chunks can be a str or a list of
            # content blocks (e.g. when reasoning/thinking is enabled).
            if isinstance(raw, list):
                text = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in raw
                )
            else:
                text = str(raw)
            if not text:
                continue
            chunks.append(text)
            if on_token is not None:
                await on_token(text)
    except Exception as e:
        err = f"\n\n[answerer error: {e}]"
        chunks.append(err)
        log.warning("answerer streaming failed: %r", e)

    answer = "".join(chunks).strip()
    step = {
        "node": "answerer",
        "duration_ms": int((time.time() - t0) * 1000),
        "output": {"chars": len(answer)},
    }
    return {"answer": answer, "trace": [step]}
