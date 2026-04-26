from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any, cast

from openai import AsyncOpenAI

from app.agents.state import GraphState
from app.config import (
    ANSWERER_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
)

TokenCallback = Callable[[str], Awaitable[None]]
on_token_var: ContextVar[TokenCallback | None] = ContextVar("on_token", default=None)


SYSTEM_BASE = (
    "You are a helpful assistant answering questions from PDFs the user "
    "uploaded.  Ground every factual claim in the retrieved excerpts below.  "
    "When the excerpts do not support an answer, say so plainly -- do not "
    "invent content.  Cite the file name and section heading in parentheses "
    "when it helps, e.g. (report.pdf, §1 Introduction).  "
    "Prefer direct quotes for numbers and definitions."
)

MULTI_SUFFIX = (
    "  Multiple documents are in scope; attribute facts to the correct file "
    "using the '## filename — section' headers in the context."
)


def build_messages(state: GraphState) -> list[dict[str, str]]:
    system = SYSTEM_BASE
    if state.get("document_ids") and len(state["document_ids"]) > 1:
        system = SYSTEM_BASE + MULTI_SUFFIX
    system += (
        "\n\n--- retrieved context ---\n"
        f"{state.get('context') or '(no context retrieved)'}\n"
        "--- end context ---"
    )
    msgs: list[dict[str, str]] = [{"role": "system", "content": system}]
    for m in state.get("history") or []:
        msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": state["query"]})
    return msgs


async def run(state: GraphState) -> dict[str, Any]:
    t0 = time.time()
    on_token = on_token_var.get()

    client = AsyncOpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY or "missing",
        default_headers={
            "HTTP-Referer": "https://localhost/chat-pdf",
            "X-Title": "chat_pdf answerer",
        },
    )
    chunks: list[str] = []
    try:
        stream = await client.chat.completions.create(
            model=ANSWERER_MODEL,
            messages=cast(Any, build_messages(state)),
            stream=True,
            extra_body={"reasoning": {"effort": "minimal", "exclude": True}},
        )
        async for ev in cast(Any, stream):
            choice = ev.choices[0] if ev.choices else None
            if not choice:
                continue
            delta = choice.delta.content if choice.delta else None
            if not delta:
                continue
            chunks.append(delta)
            if on_token is not None:
                await on_token(delta)
    except Exception as e:
        chunks.append(f"\n\n[answerer error: {e}]")

    answer = "".join(chunks).strip()
    step = {
        "node": "answerer",
        "duration_ms": int((time.time() - t0) * 1000),
        "output": {"chars": len(answer)},
    }
    return {"answer": answer, "trace": [step]}
