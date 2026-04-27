"""Embedding client behavior with mocked HTTP."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.processing import embeddings as emb


def test_needs_nomic_prefix_detects_model_name() -> None:
    assert emb.needs_nomic_prefix("nomic-embed-text") is True
    assert emb.needs_nomic_prefix("Nomic-Embed-foo") is True
    assert emb.needs_nomic_prefix("mxbai-embed-large") is False


def test_apply_prefix_respects_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(emb, "EMBEDDING_MODEL", "nomic-embed-text")
    assert emb.apply_prefix("hi", "query") == "search_query: hi"
    assert emb.apply_prefix("hi", "document") == "search_document: hi"
    monkeypatch.setattr(emb, "EMBEDDING_MODEL", "other-model")
    assert emb.apply_prefix("hi", "query") == "hi"


@pytest.mark.asyncio
async def test_embed_batch_success() -> None:
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "embeddings": [[0.0, 1.0], [1.0, 0.0]],
    }
    client.post = AsyncMock(return_value=resp)
    out = await emb.embed_batch(client, ["a", "b"])
    assert out == [[0.0, 1.0], [1.0, 0.0]]
    client.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_embed_batch_count_mismatch_raises() -> None:
    client = MagicMock()
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"embeddings": [[0.0]]}
    client.post = AsyncMock(return_value=resp)
    with pytest.raises(RuntimeError, match="expected 2 vectors"):
        await emb.embed_batch(client, ["a", "b"])


@pytest.mark.asyncio
async def test_embed_batch_http_error() -> None:
    client = MagicMock()
    req = httpx.Request("POST", "http://test/api/embed")
    client.post = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "bad", request=req, response=httpx.Response(500, request=req)
        )
    )
    with pytest.raises(httpx.HTTPStatusError):
        await emb.embed_batch(client, ["x"])


@pytest.mark.asyncio
async def test_embed_texts_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(emb, "EMBEDDING_MODEL", "plain-embed")
    monkeypatch.setattr(emb, "BATCH", 2)
    calls: list[list[str]] = []

    async def fake_batch(
        client: httpx.AsyncClient, inputs: list[str]
    ) -> list[list[float]]:
        calls.append(list(inputs))
        return [[float(i)] for i in range(len(inputs))]

    monkeypatch.setattr(emb, "embed_batch", fake_batch)
    out = await emb.embed_texts(["a", "b", "c", "d"], kind="document")
    assert len(out) == 4
    assert len(calls) == 2
    assert calls[0] == ["a", "b"]
    assert calls[1] == ["c", "d"]
