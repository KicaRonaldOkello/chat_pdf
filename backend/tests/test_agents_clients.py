"""Tests for openrouter_json — now backed by the OpenAI SDK."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.agents.clients as clients_mod
from app.agents.clients import openrouter_json


@pytest.mark.asyncio
async def test_openrouter_json_missing_api_key_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "")

    out = await openrouter_json(model="m", system="s", user="u")

    assert out is None


@pytest.mark.asyncio
async def test_openrouter_json_success_parses_choice_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(clients_mod, "OPENROUTER_BASE_URL", "https://or.test/v1")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"answer": 42}'
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.agents.clients.AsyncOpenAI", return_value=mock_client):
        out = await openrouter_json(
            model="judge", system="s", user="u", temperature=0.1
        )

    assert out == {"answer": 42}
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["temperature"] == 0.1
    assert call_kwargs["response_format"] == {"type": "json_object"}
    assert call_kwargs["model"] == "judge"


@pytest.mark.asyncio
async def test_openrouter_json_default_reasoning_is_minimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(clients_mod, "OPENROUTER_BASE_URL", "https://or.test/v1")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "{}"
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.agents.clients.AsyncOpenAI", return_value=mock_client):
        await openrouter_json(model="m", system="s", user="u")

    assert mock_client.chat.completions.create.call_args.kwargs["extra_body"] == {
        "reasoning": {"effort": "minimal"},
    }


@pytest.mark.asyncio
async def test_openrouter_json_reasoning_payload_minimal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(clients_mod, "OPENROUTER_BASE_URL", "https://or.test/v1")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "{}"
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.agents.clients.AsyncOpenAI", return_value=mock_client):
        await openrouter_json(
            model="m",
            system="s",
            user="u",
            include_reasoning=True,
            high_reasoning_effort=False,
        )

    assert mock_client.chat.completions.create.call_args.kwargs["extra_body"] == {
        "reasoning": {"effort": "minimal", "exclude": True},
    }


@pytest.mark.asyncio
async def test_openrouter_json_reasoning_payload_high(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(clients_mod, "OPENROUTER_BASE_URL", "https://or.test/v1")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "{}"
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.agents.clients.AsyncOpenAI", return_value=mock_client):
        await openrouter_json(
            model="m",
            system="s",
            user="u",
            include_reasoning=True,
            high_reasoning_effort=True,
        )

    assert mock_client.chat.completions.create.call_args.kwargs["extra_body"] == {
        "reasoning": {"effort": "high", "exclude": False},
    }


@pytest.mark.asyncio
async def test_openrouter_json_raises_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(clients_mod, "OPENROUTER_BASE_URL", "https://or.test/v1")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=ValueError("boom")
    )

    with patch("app.agents.clients.AsyncOpenAI", return_value=mock_client):
        out = await openrouter_json(model="m", system="s", user="u")

    assert out is None


@pytest.mark.asyncio
async def test_openrouter_json_garbage_content_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(clients_mod, "OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(clients_mod, "OPENROUTER_BASE_URL", "https://or.test/v1")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "not-json"
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.agents.clients.AsyncOpenAI", return_value=mock_client):
        out = await openrouter_json(model="m", system="s", user="u")

    assert out is None
