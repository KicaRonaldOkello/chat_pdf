from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import create_llm
from app.agents.prompts import get_guardrail_prompt
from app.agents.schemas import GuardrailResult
from app.agents.state import GraphState
from app.config import GUARDRAIL_MODEL

log = logging.getLogger(__name__)


def render_user(state: GraphState) -> str:
    history = state.get("history") or []
    last = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])
    doc_ids: list[str] = []
    if state.get("document_ids"):
        doc_ids = [str(d).strip() for d in (state.get("document_ids") or []) if d]
    elif state.get("document_id"):
        doc_ids = [str(state["document_id"])]
    n = len(doc_ids)
    if n == 0:
        scope = "No document ids in state (treat as unknown; prefer ALLOW for normal Q&A)."
    else:
        preview = doc_ids[:8]
        tail = "…" if len(doc_ids) > 8 else ""
        scope = (
            f"{n} document(s) in scope (uploaded for this chat). "
            f"ids: {', '.join(preview)}{tail}\n"
            f"User may ask about all of them together, compare them, or ask for "
            f"common themes; that is in scope for this feature."
        )
    return f"{scope}\n\nRecent chat history:\n{last or '(none)'}\n\nCurrent query:\n{state['query']}"


async def run(state: GraphState) -> dict[str, Any]:
    t0 = time.time()
    llm = create_llm(GUARDRAIL_MODEL)
    structured = llm.with_structured_output(GuardrailResult, method="json_mode")
    messages = [
        SystemMessage(content=get_guardrail_prompt()),
        HumanMessage(content=render_user(state)),
    ]

    result = GuardrailResult(allow=True)
    try:
        result = await structured.ainvoke(messages)
    except Exception:
        log.debug("guardrail structured output failed; defaulting to allow", exc_info=True)

    step = {
        "node": "guardrail",
        "duration_ms": int((time.time() - t0) * 1000),
        "output": result.model_dump(),
    }
    return {"guardrail": result.model_dump(), "trace": [step]}
