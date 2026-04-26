from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.agents.clients import openrouter_json
from app.agents.state import GraphState, JudgeResult
from app.config import (
    AGENT_MAX_RETRIES,
    JUDGE_MODEL,
    JUDGE_PASS_THRESHOLD,
    JUDGE_REQUEST_TIMEOUT,
)

SYSTEM = (
    "You are an impartial evaluator of retrieval-augmented answers.  Excerpts "
    "may come from more than one PDF; evaluate whether the answer uses the "
    "right material for each claim.  Given the original question, the "
    "retrieved excerpts, and the assistant's answer, score the answer on three "
    "0-10 axes:\n\n"
    "  - groundedness:  every factual claim is traceable to the excerpts\n"
    "  - relevance:     the answer actually addresses the question\n"
    "  - completeness:  supporting detail from excerpts is not omitted\n\n"
    "Also list concrete concerns (unsupported claims, missing evidence, "
    "hallucinations), and pick a verdict:\n"
    '  "pass"   -- answer is good enough to show the user\n'
    '  "retry"  -- retrieval missed; try a different retrieval strategy\n'
    '  "reject" -- answer should not be shown (e.g. clearly hallucinated)\n\n'
    'Return STRICT JSON only: {"groundedness": int, "relevance": int, '
    '"completeness": int, "concerns": [str, ...], "verdict": "pass|retry|reject"}.'
)


def render_user(state: GraphState) -> str:
    context = state.get("context") or "(no context)"
    return (
        f"Question:\n{state['query']}\n\n"
        f"Retrieved excerpts:\n{context[:8000]}\n\n"
        f"Assistant answer:\n{state.get('answer') or ''}"
    )


async def run(state: GraphState) -> dict[str, Any]:
    t0 = time.time()
    async with httpx.AsyncClient() as client:
        parsed = await openrouter_json(
            client,
            model=JUDGE_MODEL,
            system=SYSTEM,
            user=render_user(state),
            timeout=JUDGE_REQUEST_TIMEOUT,
        )

    result = JudgeResult(verdict="pass")
    if isinstance(parsed, dict):
        try:
            result = JudgeResult.model_validate(parsed)
        except ValidationError:
            pass

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
