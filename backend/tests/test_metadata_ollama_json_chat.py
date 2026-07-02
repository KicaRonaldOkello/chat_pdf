"""Ollama /api/chat JSON path used by metadata enrichment (distinct from agents.clients.ollama_json)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import app.processing.metadata as metadata


@pytest.mark.asyncio
async def test_ollama_json_chat_success_includes_num_predict_when_capped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.processing.metadata.settings.ollama_base_url", "http://ollama.test")
    monkeypatch.setattr("app.processing.metadata.settings.metadata_llm_temperature", 0.15)
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"message": {"content": '{"ok": true}'}}
    client.post = AsyncMock(return_value=resp)

    out = await metadata.ollama_json_chat(
        client,
        model="meta",
        system="sys",
        user="usr",
        timeout=55.0,
        max_output_tokens=256,
    )

    assert out == {"ok": True}
    body = client.post.call_args.kwargs["json"]
    assert body["options"]["num_predict"] == 256
    assert body["options"]["temperature"] == 0.15
    assert client.post.call_args.kwargs["timeout"] == 55.0


@pytest.mark.asyncio
async def test_ollama_json_chat_omits_num_predict_when_not_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.processing.metadata.settings.ollama_base_url", "http://ollama.test")
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"message": {"content": "{}"}}
    client.post = AsyncMock(return_value=resp)

    await metadata.ollama_json_chat(client, model="m", system="s", user="u")

    opts = client.post.call_args.kwargs["json"]["options"]
    assert "num_predict" not in opts


@pytest.mark.asyncio
async def test_ollama_json_chat_json_decode_error_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.processing.metadata.settings.ollama_base_url", "http://ollama.test")
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"message": {"content": "not valid json"}}
    client.post = AsyncMock(return_value=resp)

    out = await metadata.ollama_json_chat(client, model="m", system="s", user="u")
    assert out is None


@pytest.mark.asyncio
async def test_ollama_json_chat_http_error_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.processing.metadata.settings.ollama_base_url", "http://ollama.test")
    req = httpx.Request("POST", "http://ollama.test/api/chat")
    bad = httpx.Response(500, request=req, text="err")
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("500", request=req, response=bad)
    )
    client.post = AsyncMock(return_value=resp)

    out = await metadata.ollama_json_chat(client, model="m", system="s", user="u")
    assert out is None
