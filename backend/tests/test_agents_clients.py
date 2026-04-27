"""HTTP helpers in app.agents.clients: JSON extraction and mocked httpx."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import app.agents.clients as clients_mod
from app.agents.clients import extract_json, ollama_json, openrouter_json


def test_extract_json_strips_markdown_fence() -> None:
    raw = '```json\n{"a": 1, "b": [2]}\n```'
    assert extract_json(raw) == {"a": 1, "b": [2]}


def test_extract_json_finds_object_in_prose() -> None:
    raw = 'Here you go:\n```\n{"ok": true}\n```\nThanks.'
    assert extract_json(raw) == {"ok": True}


def test_extract_json_prefers_outer_braces() -> None:
    raw = 'noise {"nested": {"x": 1}} tail'
    out = extract_json(raw)
    assert out == {"nested": {"x": 1}}


def test_extract_json_array_slice() -> None:
    assert extract_json("prefix [1, 2] suffix") == [1, 2]


def test_extract_json_invalid_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        extract_json("not json at all")


def test_extract_json_whitespace_only_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        extract_json("   ")


@pytest.mark.asyncio
async def test_ollama_json_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clients_mod, "OLLAMA_BASE_URL", "http://ollama.test")
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"message": {"content": '{"role": "x"}'}}
    client.post = AsyncMock(return_value=resp)

    out = await ollama_json(client, model="m1", system="sys", user="usr", timeout=30.0)

    assert out == {"role": "x"}
    client.post.assert_awaited_once()
    url = client.post.call_args.args[0]
    assert url == "http://ollama.test/api/chat"
    assert client.post.call_args.kwargs["timeout"] == 30.0
    payload = client.post.call_args.kwargs["json"]
    assert payload["model"] == "m1"
    assert payload["format"] == "json"
    assert payload["stream"] is False


@pytest.mark.asyncio
async def test_ollama_json_http_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clients_mod, "OLLAMA_BASE_URL", "http://ollama.test")
    req = httpx.Request("POST", "http://ollama.test/api/chat")
    bad = httpx.Response(502, request=req, text="bad")
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("502", request=req, response=bad)
    )
    client.post = AsyncMock(return_value=resp)

    out = await ollama_json(client, model="m", system="s", user="u")
    assert out is None


@pytest.mark.asyncio
async def test_ollama_json_timeout_returns_none() -> None:
    client = MagicMock()
    client.post = AsyncMock(side_effect=httpx.TimeoutException("deadline"))

    out = await ollama_json(client, model="m", system="s", user="u", timeout=1.0)
    assert out is None


@pytest.mark.asyncio
async def test_ollama_json_connect_error_returns_none() -> None:
    client = MagicMock()
    client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))

    out = await ollama_json(client, model="m", system="s", user="u")
    assert out is None


@pytest.mark.asyncio
async def test_ollama_json_unparseable_message_returns_none() -> None:
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"message": {"content": "not-json"}}
    client.post = AsyncMock(return_value=resp)

    out = await ollama_json(client, model="m", system="s", user="u")
    assert out is None


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
