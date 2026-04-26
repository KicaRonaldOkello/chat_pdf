from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.config import (
    METADATA_LLM_TEMPERATURE,
    METADATA_REQUEST_TIMEOUT,
    OLLAMA_BASE_URL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    ROUTER_REQUEST_TIMEOUT,
)

log = logging.getLogger(__name__)

JSON_CODEBLOCK_RE = re.compile(
    r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE
)


def extract_json(raw: str) -> Any:
    text = JSON_CODEBLOCK_RE.sub("", (raw or "").strip()).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                continue
    return json.loads(text)


async def ollama_json(
    client: httpx.AsyncClient,
    *,
    model: str,
    system: str,
    user: str,
    timeout: float = METADATA_REQUEST_TIMEOUT,
    temperature: float = METADATA_LLM_TEMPERATURE,
) -> Any | None:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": temperature},
    }

    try:
        r = await client.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "")
        return extract_json(content)
    except httpx.HTTPStatusError as e:
        log.warning(
            "ollama_json HTTP %s (model=%s): %s | body: %s",
            e.response.status_code,
            model,
            e,
            (e.response.text or "")[:500],
        )
    except httpx.TimeoutException as e:
        log.warning(
            "ollama_json timeout (model=%s timeout_s=%s): %s %r",
            model,
            timeout,
            type(e).__name__,
            e,
        )
    except httpx.RequestError as e:
        log.warning(
            "ollama_json request failed (model=%s): %s %r url=%s",
            model,
            type(e).__name__,
            e,
            f"{OLLAMA_BASE_URL}/api/chat",
        )
    except Exception as e:
        log.warning(
            "ollama_json failed (model=%s): %s %r",
            model,
            type(e).__name__,
            e,
            exc_info=True,
        )
    return None


async def openrouter_json(
    client: httpx.AsyncClient,
    *,
    model: str,
    system: str,
    user: str,
    timeout: float = ROUTER_REQUEST_TIMEOUT,
    temperature: float = 0.0,
    include_reasoning: bool = False,
    high_reasoning_effort: bool = False,
) -> Any | None:
    if not OPENROUTER_API_KEY:
        log.warning("OPENROUTER_API_KEY not set; skipping judge call")
        return None
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": temperature,
    }
    if include_reasoning:
        payload["reasoning"] = (
            {"effort": "high", "exclude": False}
            if high_reasoning_effort
            else {"effort": "minimal", "exclude": True}
        )
    try:
        r = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://localhost/chat-pdf",
                "X-Title": "chat_pdf agent judge",
            },
            timeout=timeout,
        )
        if r.status_code >= 400:
            log.warning(
                "openrouter_json HTTP %d (model=%s): %s",
                r.status_code,
                model,
                r.text[:500],
            )
            return None
        data = r.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return extract_json(content)
    except Exception as e:
        log.warning("openrouter_json failed (model=%s): %r", model, e)
        return None
