"""Conditional edge (routing) functions for the agent graph.

Following the agentic-rag-for-dummies pattern, routing logic is separated from
the graph builder into its own module.  Each function takes the current state
and returns a string key that maps to the next node.
"""

from __future__ import annotations

from langgraph.graph import END

from app.agents.state import GraphState
from app.config import AGENT_MAX_RETRIES


def after_guardrail(state: GraphState) -> str:
    """Route after the guardrail node: allow → router, reject → reject."""
    g = state.get("guardrail") or {}
    return "router" if g.get("allow", True) else "reject"


def after_judge(state: GraphState) -> str:
    """Route after the judge node: retry → bump_attempts (up to max), else END."""
    j = state.get("judge") or {}
    attempts = state.get("attempts", 0)
    verdict = j.get("verdict", "pass")
    if verdict == "retry" and attempts < AGENT_MAX_RETRIES:
        return "router"
    return END
