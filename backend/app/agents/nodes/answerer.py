from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.journey import JourneyLogger
from app.agents.llm_factory import LLMConfig, get_llm
from app.agents.prompts import get_answerer_system_prompt
from app.agents.state import GraphState

TokenCallback = Callable[[str], Awaitable[None]]
on_token_var: ContextVar[TokenCallback | None] = ContextVar("on_token", default=None)

import logging as _logging

log = _logging.getLogger(__name__)


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
    logger = JourneyLogger("answerer")
    logger.log_start()

    on_token = on_token_var.get()
    context_size = len(state.get("context", ""))
    logger.log_info(f"Context size: {context_size} chars")

    llm = get_llm(LLMConfig.ANSWERER)
    messages = _build_langchain_messages(state)

    chunks: list[str] = []
    # Total deadline for the entire streaming call — prevents hangs when
    # the LLM provider stops sending tokens without raising an error.
    _STREAM_DEADLINE = 120  # seconds
    try:
        async with asyncio.timeout(_STREAM_DEADLINE):
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
    except TimeoutError:
        err = "\n\n[answerer timed out after 120s]"
        chunks.append(err)
        logger.log_error("Streaming timed out after 120s")
        log.warning("answerer streaming timed out after %.0fs", _STREAM_DEADLINE)
    except Exception as e:
        err = f"\n\n[answerer error: {e}]"
        chunks.append(err)
        logger.log_error("Streaming failed", e)
        log.warning("answerer streaming failed: %r", e)

    answer = "".join(chunks).strip()
    logger.log_info(f"Generated answer: {len(answer)} chars")

    journey_data = logger.log_complete({
        "context_size": context_size,
        "answer_length": len(answer),
    })

    step = {
        "node": "answerer",
        "duration_ms": journey_data["duration_ms"],
        "output": {"chars": len(answer)},
    }
    return {"answer": answer, "trace": [step], "journey": [journey_data]}
