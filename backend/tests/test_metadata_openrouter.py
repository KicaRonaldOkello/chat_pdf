"""OpenRouter enrichment: chunk sizing, output caps, and retry behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app import clients
from app.processing.metadata import enrich_via_openrouter, pack_section_chunks
from app.processing.structure import ElementRef, Section
from app.settings import settings


def _section(i: int) -> Section:
    return Section(
        id=f"s{i}",
        title=f"Section {i}",
        level=0,
        path=f"Section {i}",
        page_range=[i, i],
        elements=[
            ElementRef(
                id=f"e{i}",
                type="text",
                page=i,
                text=f"Body text number {i}.",
            )
        ],
        children=[],
    )


def test_pack_section_chunks_caps_by_sections() -> None:
    sections = [_section(i) for i in range(100)]

    chunks = pack_section_chunks(
        sections,
        filename="f.pdf",
        num_pages=100,
        token_budget=1_000_000,  # input budget alone would return one chunk
        max_sections_per_chunk=40,
    )

    assert [len(c) for c in chunks] == [40, 40, 20]


def test_pack_section_chunks_small_doc_stays_single() -> None:
    sections = [_section(i) for i in range(10)]

    chunks = pack_section_chunks(
        sections,
        filename="f.pdf",
        num_pages=10,
        token_budget=1_000_000,
        max_sections_per_chunk=40,
    )

    assert len(chunks) == 1
    assert len(chunks[0]) == 10


@pytest.mark.asyncio
async def test_openrouter_json_passes_max_tokens(monkeypatch) -> None:
    fake_client = AsyncMock()
    fake_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))]
    )
    monkeypatch.setattr(clients.settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(clients, "AsyncOpenAI", lambda **_kwargs: fake_client)

    result = await clients.openrouter_json(
        model="m", system="s", user="u", max_tokens=8_000
    )

    assert result == {"ok": True}
    assert fake_client.chat.completions.create.await_args.kwargs["max_tokens"] == 8_000


@pytest.mark.asyncio
async def test_enrich_via_openrouter_retries_failed_chunk(monkeypatch) -> None:
    root = Section(
        id="root",
        title="R",
        level=0,
        path="Document",
        page_range=[1, 2],
        elements=[],
        children=[_section(1), _section(2)],
    )
    calls = {"n": 0}

    async def fake_json(**kwargs) -> dict | None:
        calls["n"] += 1
        return None if calls["n"] == 1 else {}

    monkeypatch.setattr(settings, "openrouter_api_key", "sk-test")
    with patch("app.processing.metadata.openrouter_json", side_effect=fake_json):
        result = await enrich_via_openrouter(
            root, document_id="doc-1", filename="f.pdf", num_pages=2
        )

    assert calls["n"] == 2  # one failed attempt + one retry
    assert result is not None
