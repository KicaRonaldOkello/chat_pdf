"""Graph state definition for the agent pipeline.

The graph state is a TypedDict that flows through every node in the LangGraph
pipeline.  Structured output schemas (GuardrailResult, RouterPlan, JudgeResult)
live in the separate ``schemas`` module.
"""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, Literal, TypedDict


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class GraphState(TypedDict, total=False):
    document_id: str
    document_ids: list[str]
    query: str
    history: list[ChatMessage]

    guardrail: dict[str, Any]
    plan: dict[str, Any]
    retrieved: list[dict[str, Any]]
    context: str
    answer: str
    judge: dict[str, Any]

    attempts: int
    retrieval_attempts: int
    retrieval_sufficient: bool
    gap_query: str
    trace: Annotated[list[dict[str, Any]], add]
    journey: Annotated[list[dict[str, Any]], add]
    final_route: str
