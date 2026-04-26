from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import answerer, guardrail, judge, retrieve, router
from app.agents.state import GraphState
from app.config import AGENT_MAX_RETRIES

log = logging.getLogger(__name__)


def after_guardrail(state: GraphState) -> str:
    g = state.get("guardrail") or {}
    return "router" if g.get("allow", True) else "reject"


def after_judge(state: GraphState) -> str:
    j = state.get("judge") or {}
    attempts = state.get("attempts", 0)
    verdict = j.get("verdict", "pass")
    if verdict == "retry" and attempts < AGENT_MAX_RETRIES:
        return "router"
    return END


async def reject_node(state: GraphState) -> dict[str, Any]:
    g = state.get("guardrail") or {}
    reason = g.get("reason") or "Query rejected by safety policy."
    return {
        "answer": reason,
        "final_route": "reject",
        "trace": [{"node": "reject", "output": {"reason": reason}}],
    }


async def bump_attempts(state: GraphState) -> dict[str, Any]:
    return {"attempts": state.get("attempts", 0) + 1}


def build_graph() -> Any:
    g = StateGraph(GraphState)

    g.add_node("guardrail", guardrail.run)
    g.add_node("router", router.run)
    g.add_node("retrieve", retrieve.run)
    g.add_node("answerer", answerer.run)
    g.add_node("judge", judge.run)
    g.add_node("reject", reject_node)
    g.add_node("bump_attempts", bump_attempts)

    g.add_edge(START, "guardrail")
    g.add_conditional_edges(
        "guardrail", after_guardrail, {"router": "router", "reject": "reject"}
    )
    g.add_edge("router", "retrieve")
    g.add_edge("retrieve", "answerer")
    g.add_edge("answerer", "judge")
    g.add_conditional_edges("judge", after_judge, {"router": "bump_attempts", END: END})
    g.add_edge("bump_attempts", "router")
    g.add_edge("reject", END)

    return g.compile()


_graph: Any | None = None


def get_graph() -> Any:
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
