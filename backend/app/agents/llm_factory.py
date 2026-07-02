"""LLM factory for creating configured language model instances."""

from __future__ import annotations

from enum import Enum
from typing import Any

from langchain_openai import ChatOpenAI

from app.settings import settings


def create_llm(
    model: str,
    *,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    extra_headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> ChatOpenAI:
    """Return a LangChain ``ChatOpenAI`` pointed at OpenRouter."""
    headers: dict[str, str] = {
        "HTTP-Referer": "https://localhost/chat-pdf",
        "X-Title": "chat_pdf",
    }
    if extra_headers:
        headers.update(extra_headers)
    return ChatOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key or "missing",
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        default_headers=headers,
        **kwargs,
    )


class LLMConfig(Enum):
    GUARDRAIL = ("guardrail_model", 0.0)
    ROUTER = ("router_model", 0.0)
    ANSWERER = ("answerer_model", 0.0)
    JUDGE = ("judge_model", 0.0)
    VISION = ("vision_model", 0.0)


def get_llm(config: LLMConfig, **kwargs: Any) -> ChatOpenAI:
    model_attr, temperature = config.value
    model_name = getattr(settings, model_attr)
    return create_llm(model_name, temperature=temperature, **kwargs)
