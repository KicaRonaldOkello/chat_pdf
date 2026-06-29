"""Pydantic models for structured LLM output in the agent pipeline.

Following the agentic-rag-for-dummies pattern, structured output schemas live
in a dedicated module separate from the graph state definition.  These models
are used with LangChain's `with_structured_output()` or for manual validation
of LLM JSON responses.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GuardrailResult(BaseModel):
    """Result of the guardrail safety classifier."""

    allow: bool
    category: Literal["ok", "jailbreak", "inappropriate", "out_of_scope"] = "ok"
    reason: str = ""

    model_config = {"extra": "ignore", "str_strip_whitespace": True}


class RouterPlan(BaseModel):
    """Retrieval plan produced by the router node."""

    route: Literal["structural", "semantic", "hybrid"] = "semantic"
    section_ids: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    rewritten_query: str = ""
    rationale: str = ""

    model_config = {"extra": "ignore", "str_strip_whitespace": True}


class JudgeResult(BaseModel):
    """Evaluation scores produced by the judge node."""

    groundedness: int = Field(default=0, ge=0, le=10)
    relevance: int = Field(default=0, ge=0, le=10)
    completeness: int = Field(default=0, ge=0, le=10)
    concerns: list[str] = Field(default_factory=list)
    verdict: Literal["pass", "retry", "reject"] = "pass"

    model_config = {"extra": "ignore", "str_strip_whitespace": True}
