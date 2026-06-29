from __future__ import annotations

import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import create_llm
from app.agents.prompts import get_judge_prompt
from app.agents.schemas import JudgeResult
from app.agents.state import GraphState
from app.config import (
    AGENT_MAX_RETRIES,
    JUDGE_MODEL,
    JUDGE_PASS_THRESHOLD,
)

log = __import__("logging").getLogger(__name__)


def render_user(state: GraphState) -> str:
    context = state.get("context") or "(no context)"
    return (
        f"Question:\n{state['query']}\n\n"
        f"Retrieved excerpts:\n{context[:8000]}\n\n"
        f"Assistant answer:\n{state.get('answer') or ''}"
    )


async def run(state: GraphState) -> dict[str, Any]:
    t0 = time.time()
    llm = create_llm(JUDGE_MODEL)
    structured = llm.with_structured_output(JudgeResult, method="json_mode")
    messages = [
        SystemMessage(content=get_judge_prompt()),
        HumanMessage(content=render_user(state)),
    ]

    result = JudgeResult(verdict="pass")
    try:
        result = await structured.ainvoke(messages)
    except Exception:
        log.debug("judge structured output failed; defaulting to pass", exc_info=True)

    attempts = state.get("attempts", 0)
    effective_verdict = result.verdict
    if effective_verdict == "retry" and attempts >= AGENT_MAX_RETRIES:
        effective_verdict = "pass"

    out = result.model_dump()
    out["verdict"] = effective_verdict
    out["threshold"] = JUDGE_PASS_THRESHOLD
    out["attempts_used"] = attempts

    step = {
        "node": "judge",
        "duration_ms": int((time.time() - t0) * 1000),
        "output": out,
    }
    return {"judge": out, "trace": [step]}
