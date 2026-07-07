"""Vector store tests — mocking the Postgres session."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.processing import vectorstore as vs
from app.processing.chunking import Chunk


def _make_chunk(**overrides) -> Chunk:
    defaults = {
        "chunk_id": "d::text::0",
        "document_id": "d",
        "element_ids": ["e1"],
        "type": "text",
        "section_path": "S",
        "page": 1,
        "text_for_embedding": "t",
        "display_text": "t",
    }
    defaults.update(overrides)
    return Chunk(**defaults)


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    return session


@pytest.mark.asyncio
async def test_upsert_chunks_skips_empty() -> None:
    await vs.upsert_chunks([], [])


@pytest.mark.asyncio
async def test_upsert_chunks_calls_execute() -> None:
    session = _mock_session()
    chunks = [_make_chunk()]
    vectors = [[0.1, 0.2, 0.3]]
    with patch.object(vs, "_session", return_value=session):
        await vs.upsert_chunks(chunks, vectors)
    session.execute.assert_called()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_empty_ids() -> None:
    result = await vs.search([], [0.1, 0.2], 5)
    assert result == []


@pytest.mark.asyncio
async def test_search_returns_hits_with_score() -> None:
    session = _mock_session()
    row = MagicMock()
    row.chunk_id = "d::t::0"
    row.document_id = "d"
    row.element_ids = ["e1"]
    row.type = "text"
    row.section_path = "S"
    row.page = 1
    row.display_text = "hello"
    row.bbox = None
    row.page_size = None
    row.extra = {}
    row._score = 0.95
    session.execute = AsyncMock(return_value=[row])

    with patch.object(vs, "_session", return_value=session):
        result = await vs.search("d", [0.1, 0.2], 5)

    assert len(result) == 1
    assert result[0]["_score"] == 0.95
    assert result[0]["chunk_id"] == "d::t::0"


@pytest.mark.asyncio
async def test_fetch_by_section_empty_paths() -> None:
    result = await vs.fetch_by_section("d", [])
    assert result == []


@pytest.mark.asyncio
async def test_fetch_by_section_returns_hits() -> None:
    session = _mock_session()
    row = MagicMock()
    row.chunk_id = "d::t::0"
    row.document_id = "d"
    row.element_ids = []
    row.type = "text"
    row.section_path = "A"
    row.page = 2
    row.display_text = "x"
    row.bbox = None
    row.page_size = None
    row.extra = None
    session.execute = AsyncMock(return_value=[row])

    with patch.object(vs, "_session", return_value=session):
        result = await vs.fetch_by_section("d", ["A"])

    assert len(result) == 1
    assert result[0]["section_path"] == "A"
    assert result[0]["_score"] == 1.0  # structural has fixed score


@pytest.mark.asyncio
async def test_delete_doc_executes_delete() -> None:
    session = _mock_session()
    with patch.object(vs, "_session", return_value=session):
        await vs.delete_doc("d")
    session.execute.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_collection_is_noop() -> None:
    await vs.ensure_collection()


@pytest.mark.asyncio
async def test_fetch_by_section_multi_single_doc() -> None:
    session = _mock_session()
    row = MagicMock()
    row.chunk_id = "d::t::0"
    row.document_id = "d"
    row.element_ids = []
    row.type = "text"
    row.section_path = "A"
    row.page = 1
    row.display_text = "x"
    row.bbox = None
    row.page_size = None
    row.extra = None
    session.execute = AsyncMock(return_value=[row])

    with patch.object(vs, "_session", return_value=session):
        result = await vs.fetch_by_section_multi({"d": ["A"]})

    assert len(result) == 1
    assert result[0]["section_path"] == "A"
