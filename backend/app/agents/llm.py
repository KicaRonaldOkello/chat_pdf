"""LangChain LLM factory configured for OpenRouter.

Following the agentic-rag-for-dummies pattern, all LLM instantiation goes through a
single factory so that base URL, API key, and shared headers are applied consistently.
"""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from app.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL


def create_llm(
    model: str,
    *,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    extra_headers: dict[str, str] | None = None,
    **kwargs: Any,
) -> ChatOpenAI:
    """Return a LangChain ``ChatOpenAI`` pointed at OpenRouter.

    Args:
        model: OpenRouter model string (e.g. ``"google/gemini-2.5-flash-lite"``).
        temperature: Sampling temperature (0.0 = deterministic).
        max_tokens: Optional output token cap.
        extra_headers: Additional HTTP headers to merge with the defaults.
        **kwargs: Forwarded to ``ChatOpenAI`` (e.g. ``model_kwargs`` for
            OpenRouter-specific ``reasoning`` parameters).
    """
    headers: dict[str, str] = {
        "HTTP-Referer": "https://localhost/chat-pdf",
        "X-Title": "chat_pdf",
    }
    if extra_headers:
        headers.update(extra_headers)

    return ChatOpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY or "missing",
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        default_headers=headers,
        **kwargs,
    )
