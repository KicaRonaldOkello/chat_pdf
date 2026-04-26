from __future__ import annotations

from operator import add
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field


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
    trace: Annotated[list[dict[str, Any]], add]
    final_route: str


class GuardrailResult(BaseModel):
    allow: bool
    category: Literal["ok", "jailbreak", "inappropriate", "out_of_scope"] = "ok"
    reason: str = ""

    model_config = {"extra": "ignore", "str_strip_whitespace": True}


class RouterPlan(BaseModel):
    route: Literal["structural", "semantic", "hybrid"] = "semantic"
    section_ids: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    rewritten_query: str = ""
    rationale: str = ""

    model_config = {"extra": "ignore", "str_strip_whitespace": True}


class JudgeResult(BaseModel):
    groundedness: int = Field(default=0, ge=0, le=10)
    relevance: int = Field(default=0, ge=0, le=10)
    completeness: int = Field(default=0, ge=0, le=10)
    concerns: list[str] = Field(default_factory=list)
    verdict: Literal["pass", "retry", "reject"] = "pass"

    model_config = {"extra": "ignore", "str_strip_whitespace": True}
