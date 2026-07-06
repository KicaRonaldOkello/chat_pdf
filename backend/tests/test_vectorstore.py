"""Vector store helpers with Qdrant client mocked."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from qdrant_client.http import models as qm

from app.processing import vectorstore as vs
from app.processing.chunking import Chunk


def test_point_id_stable_for_same_chunk() -> None:
    a = vs.point_id("doc::text::0")
    b = vs.point_id("doc::text::0")
    c = vs.point_id("doc::text::1")
    assert a == b
    assert a != c


def test_normalize_document_ids() -> None:
    assert vs.normalize_document_ids("d1") == ["d1"]
    assert vs.normalize_document_ids(["a", "b"]) == ["a", "b"]


def test_document_id_match_condition_single_vs_many() -> None:
    one = vs.document_id_match_condition(["x"])
    assert one.key == "document_id"
    assert isinstance(one.match, (qm.MatchValue, qm.MatchAny))
    many = vs.document_id_match_condition(["x", "y"])
    assert isinstance(many.match, qm.MatchAny)


def test_upsert_sync_skips_empty_chunks() -> None:
    vs.upsert_sync([], [])


def test_upsert_sync_calls_qdrant_with_point_structs(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_q = MagicMock()
    monkeypatch.setattr(vs, "client", lambda: mock_q)
    chunks = [
        Chunk(
            chunk_id="d::text::0",
            document_id="d",
            element_ids=["e1"],
            type="text",
            section_path="S",
            page=1,
            text_for_embedding="t",
            display_text="t",
        )
    ]
    vectors = [[0.1, 0.2, 0.3]]
    vs.upsert_sync(chunks, vectors)
    mock_q.upsert.assert_called_once()
    kwargs = mock_q.upsert.call_args.kwargs
    assert kwargs["collection_name"] == vs.settings.qdrant_collection
    points = kwargs["points"]
    assert len(points) == 1
    assert points[0].id == vs.point_id("d::text::0")
    assert points[0].vector == vectors[0]
    assert points[0].payload["chunk_id"] == "d::text::0"


@pytest.mark.asyncio
async def test_ensure_collection_delegates_to_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []

    def sync() -> None:
        called.append(True)

    monkeypatch.setattr(vs, "ensure_collection_sync", sync)
    await vs.ensure_collection()
    assert called == [True]
