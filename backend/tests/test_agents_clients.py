"""HTTP helpers in app.agents.clients: JSON extraction and mocked httpx."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import app.agents.clients as clients_mod
from app.agents.clients import openrouter_json


@pytest.mark.asyncio
async def test_openrouter_json_missing_api_key_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "")
    client = MagicMock()
    client.post = AsyncMock()

    out = await openrouter_json(client, model="m", system="s", user="u")

    assert out is None
    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_openrouter_json_http_4xx_returns_none_without_parsing_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(clients_mod, "OPENROUTER_BASE_URL", "https://or.test/v1")
    client = MagicMock()
    resp = MagicMock(spec=["status_code", "text"])
    resp.status_code = 429
    resp.text = "rate limited"
    client.post = AsyncMock(return_value=resp)

    out = await openrouter_json(client, model="m", system="s", user="u")

    assert out is None


@pytest.mark.asyncio
async def test_openrouter_json_success_parses_choice_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(clients_mod, "OPENROUTER_BASE_URL", "https://or.test/v1")
    client = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": '{"answer": 42}'}}],
    }
    client.post = AsyncMock(return_value=resp)

    out = await openrouter_json(client, model="judge", system="s", user="u", temperature=0.1)

    assert out == {"answer": 42}
    hdrs = client.post.call_args.kwargs["headers"]
    assert hdrs["Authorization"] == "Bearer sk-test"
    body = client.post.call_args.kwargs["json"]
    assert body["temperature"] == 0.1
    assert body["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_openrouter_json_reasoning_payload_minimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(clients_mod, "OPENROUTER_BASE_URL", "https://or.test/v1")
    client = MagicMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"choices": [{"message": {"content": "{}"}}]}
    client.post = AsyncMock(return_value=resp)

    await openrouter_json(
        client,
        model="m",
        system="s",
        user="u",
        include_reasoning=True,
        high_reasoning_effort=False,
    )
    assert client.post.call_args.kwargs["json"]["reasoning"] == {
        "effort": "minimal",
        "exclude": True,
    }


@pytest.mark.asyncio
async def test_openrouter_json_reasoning_payload_high(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(clients_mod, "OPENROUTER_BASE_URL", "https://or.test/v1")
    client = MagicMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"choices": [{"message": {"content": "{}"}}]}
    client.post = AsyncMock(return_value=resp)

    await openrouter_json(
        client,
        model="m",
        system="s",
        user="u",
        include_reasoning=True,
        high_reasoning_effort=True,
    )
    assert client.post.call_args.kwargs["json"]["reasoning"] == {
        "effort": "high",
        "exclude": False,
    }


@pytest.mark.asyncio
async def test_openrouter_json_response_json_raises_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(clients_mod, "OPENROUTER_BASE_URL", "https://or.test/v1")
    client = MagicMock()
    resp = MagicMock(status_code=200)
    resp.json.side_effect = ValueError("not valid json")
    client.post = AsyncMock(return_value=resp)

    out = await openrouter_json(client, model="m", system="s", user="u")
    assert out is None


@pytest.mark.asyncio
async def test_openrouter_json_garbage_content_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(clients_mod, "OPENROUTER_BASE_URL", "https://or.test/v1")
    client = MagicMock()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"choices": [{"message": {"content": "not-json"}}]}
    client.post = AsyncMock(return_value=resp)

    out = await openrouter_json(client, model="m", system="s", user="u")
    assert out is None
