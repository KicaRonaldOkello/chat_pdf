"""Conditional edge (routing) functions for the agent graph.

Following the agentic-rag-for-dummies pattern, routing logic is separated from
the graph builder into its own module.  Each function takes the current state
and returns a string key that maps to the next node.
"""

from __future__ import annotations

from langgraph.graph import END

from app.agents.state import GraphState
from app.config import AGENT_MAX_RETRIES, IMAGE_AUTO_VISION_SCORE, RETRIEVAL_MAX_RETRIES


def after_guardrail(state: GraphState) -> str:
    """Route after the guardrail node: allow → router, reject → reject."""
    g = state.get("guardrail") or {}
    return "router" if g.get("allow", True) else "reject"


# Configurable threshold for auto-triggering vision analysis on high-score images


def after_retrieve(state: GraphState) -> str:
    """Route after retrieval: vision → retrieval_judge, or retrieval_judge directly."""
    plan = state.get("plan") or {}
    if plan.get("needs_vision"):
        return "vision"
    # Only auto-trigger vision for highly-ranked unanalyzed image chunks.
    # Low-ranked images that happen to appear in the top-k aren't worth
    # the cost of a vision-model call.
    for h in state.get("retrieved") or []:
        if h.get("type") == "image" and not h.get("vision_analyzed", False):
            score = float(h.get("rerank_score", h.get("_score", 0)) or 0)
            if score >= IMAGE_AUTO_VISION_SCORE:
                return "vision"
    return "retrieval_judge"


def after_retrieval_judge(state: GraphState) -> str:
    """Route after the retrieval judge: retry → retrieve, or continue → answerer."""
    if not state.get("retrieval_sufficient", True):
        attempts = state.get("retrieval_attempts", 0)
        if attempts < max(1, RETRIEVAL_MAX_RETRIES):
            return "retrieve"
    return "answerer"


def after_judge(state: GraphState) -> str:
    """Route after the judge node: retry → bump_attempts (up to max), else END."""
    j = state.get("judge") or {}
    attempts = state.get("attempts", 0)
    verdict = j.get("verdict", "pass")
    if verdict == "retry" and attempts < AGENT_MAX_RETRIES:
        return "router"
    return END
