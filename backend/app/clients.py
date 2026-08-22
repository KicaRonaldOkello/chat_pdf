from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.settings import settings

log = logging.getLogger(__name__)


async def openrouter_json(
    *,
    model: str,
    system: str,
    user: str,
    timeout: float | None = None,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    include_reasoning: bool = False,
    high_reasoning_effort: bool = False,
) -> Any | None:
    """Call OpenRouter's chat/completions with structured JSON output.

    Uses the OpenAI SDK so that OpenRouter-specific parameters (notably
    ``reasoning``) travel through ``extra_body`` — the officially documented
    way to pass provider extensions.
    """
    if timeout is None:
        timeout = settings.router_request_timeout
    if not settings.openrouter_api_key:
        log.warning("OPENROUTER_API_KEY not set; skipping openrouter call")
        return None

    client = AsyncOpenAI(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
        default_headers={
            "HTTP-Referer": "https://localhost/chat-pdf",
            "X-Title": "chat_pdf metadata",
        },
        timeout=timeout,
    )

    extra_body: dict[str, Any] = {}
    if include_reasoning:
        extra_body["reasoning"] = (
            {"effort": "high", "exclude": False}
            if high_reasoning_effort
            else {"effort": "minimal", "exclude": True}
        )
    else:
        # gpt-oss-120b requires reasoning; "none" is not a recognised effort
        # value.  Use "minimal" to keep latency as low as possible while
        # still satisfying the provider requirement.
        extra_body["reasoning"] = {"effort": "minimal"}

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
        )
        content = response.choices[0].message.content
        return json.loads(content) if content else None
    except Exception as e:
        log.warning("openrouter_json failed (model=%s): %r", model, e)
        return None
