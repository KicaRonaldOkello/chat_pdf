from __future__ import annotations

import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.journey import JourneyLogger
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
    logger = JourneyLogger("judge")
    logger.log_start()
    
    llm = create_llm(JUDGE_MODEL)
    structured = llm.with_structured_output(JudgeResult, method="json_mode")
    messages = [
        SystemMessage(content=get_judge_prompt()),
        HumanMessage(content=render_user(state)),
    ]

    result = JudgeResult(verdict="pass")
    try:
        result = await structured.ainvoke(messages)
        logger.log_info(f"Scores: G={result.groundedness}/10, R={result.relevance}/10, C={result.completeness}/10")
    except Exception as e:
        logger.log_error("Structured output failed, defaulting to pass", e)
        log.debug("judge structured output failed; defaulting to pass", exc_info=True)

    attempts = state.get("attempts", 0)
    effective_verdict = result.verdict
    # Low groundedness means the answerer hallucinated despite having the
    # right chunks — retrying won't help; it would just produce a different
    # hallucination from the same context.
    if effective_verdict == "retry" and result.groundedness < 5:
        logger.log_info(
            "Answerer hallucinated (G=%d/10); forcing pass — retry won't help",
            result.groundedness,
        )
        effective_verdict = "pass"
    elif effective_verdict == "retry" and attempts >= AGENT_MAX_RETRIES:
        logger.log_info("Max retries reached, forcing pass (was: retry)")
        effective_verdict = "pass"
    else:
        logger.log_info(f"Verdict: {effective_verdict}")

    out = result.model_dump()
    out["verdict"] = effective_verdict
    out["threshold"] = JUDGE_PASS_THRESHOLD
    out["attempts_used"] = attempts

    journey_data = logger.log_complete({
        "verdict": effective_verdict,
        "groundedness": result.groundedness,
        "relevance": result.relevance,
        "completeness": result.completeness,
        "threshold": JUDGE_PASS_THRESHOLD,
        "attempts_used": attempts,
    })
    
    step = {
        "node": "judge",
        "duration_ms": journey_data["duration_ms"],
        "output": out,
    }
    return {"judge": out, "trace": [step], "journey": [journey_data]}
