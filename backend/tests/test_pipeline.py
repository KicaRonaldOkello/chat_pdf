"""process_document wiring: mock filesystem, DB session, structure, and vector I/O."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from app.db.repositories.document_state import DocumentStatus
from app.processing.pipeline import process_document
from app.processing.structure import ElementRef, Section


def _discard_background_task(coro) -> None:
    """spawn_background receives a coroutine; if the real scheduler is patched out, close it."""
    close = getattr(coro, "close", None)
    if callable(close):
        close()


def _minimal_root() -> Section:
    return Section(
        id="root",
        title="R",
        level=0,
        path="Document",
        page_range=[1, 1],
        elements=[
            ElementRef(id="e1", type="text", page=1, text="Hello"),
        ],
        children=[],
    )


def _fake_db_session(repo: MagicMock):
    session = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def cm():
        yield session, repo

    return cm, session


@pytest.mark.asyncio
async def test_process_document_unknown_doc_returns_early() -> None:
    repo = MagicMock()
    repo.get_status = AsyncMock(return_value=None)
    cm, _ = _fake_db_session(repo)

    with (
        patch("app.processing.pipeline.document_data.document_db_session", cm),
        patch(
            "app.processing.pipeline.document_data.pull_source_pdf_to_tempfile",
            new_callable=MagicMock,
        ) as pull,
        patch(
            "app.processing.pipeline.document_data.release_source_temp_path",
            new_callable=MagicMock,
        ) as release,
        patch(
            "app.processing.pipeline.spawn_background",
            side_effect=_discard_background_task,
        ) as bg,
    ):
        await process_document("missing-id")

    pull.assert_not_called()
    release.assert_not_called()
    bg.assert_not_called()


@pytest.mark.asyncio
async def test_process_document_pull_failure_sets_error_status() -> None:
    repo = MagicMock()
    repo.get_status = AsyncMock(
        return_value=DocumentStatus(
            status="queued",
            stage="queued",
            progress=0.0,
            filename="f.pdf",
        )
    )
    repo.set_status = AsyncMock()
    cm, session = _fake_db_session(repo)
    session.commit = AsyncMock()

    err = OSError("no pdf")

    with (
        patch("app.processing.pipeline.document_data.document_db_session", cm),
        patch(
            "app.processing.pipeline.document_data.pull_source_pdf_to_tempfile",
            side_effect=err,
        ),
        patch(
            "app.processing.pipeline.document_data.release_source_temp_path",
            new_callable=MagicMock,
        ) as release,
        patch(
            "app.processing.pipeline.spawn_background",
            side_effect=_discard_background_task,
        ) as bg,
    ):
        await process_document("doc-1")

    repo.set_status.assert_awaited()
    args, _kw = repo.set_status.call_args
    assert args[0] == "doc-1"
    st: DocumentStatus = args[1]
    assert st.status == "error"
    assert "load source PDF" in st.stage
    assert st.error is not None
    session.commit.assert_awaited()
    release.assert_not_called()
    bg.assert_not_called()


@pytest.mark.asyncio
async def test_process_document_happy_path_ready_and_spawns_background() -> None:
    root = _minimal_root()
    repo = MagicMock()
    repo.get_status = AsyncMock(
        return_value=DocumentStatus(
            status="queued",
            stage="queued",
            progress=0.0,
            filename="paper.pdf",
        )
    )
    repo.update_status = AsyncMock()
    repo.save_tree = AsyncMock()
    cm, session = _fake_db_session(repo)
    session.commit = AsyncMock()

    pdf_path = Path("/tmp/fake-unit-test.pdf")

    with (
        patch("app.processing.pipeline.document_data.document_db_session", cm),
        patch(
            "app.processing.pipeline.document_data.pull_source_pdf_to_tempfile",
            return_value=pdf_path,
        ),
        patch(
            "app.processing.pipeline.document_data.release_source_temp_path",
            new_callable=MagicMock,
        ) as release,
        patch("app.processing.pipeline.structure.partition", return_value=(root, [], 3, [])),
        patch("app.processing.pipeline.tables.enrich_tables", new_callable=AsyncMock),
        patch("app.processing.pipeline.images.enrich_images", new_callable=AsyncMock),
        patch("app.processing.pipeline.chunking.build_chunks", return_value=[]),
        patch("app.processing.pipeline.vectorstore.ensure_collection", new_callable=AsyncMock),
        patch("app.processing.pipeline.embeddings.embed_texts", new_callable=AsyncMock),
        patch(
            "app.processing.pipeline.vectorstore.upsert_chunks", new_callable=AsyncMock
        ) as upsert,
        patch(
            "app.processing.pipeline.spawn_background",
            side_effect=_discard_background_task,
        ) as bg,
    ):
        await process_document("doc-42")

    release.assert_called_once_with(pdf_path)
    upsert.assert_not_awaited()
    repo.save_tree.assert_awaited_once_with("doc-42", ANY)
    final = repo.update_status.await_args_list[-1]
    assert final.args[0] == "doc-42"
    assert final.kwargs.get("status") == "ready"
    assert final.kwargs.get("progress") == 1.0
    bg.assert_called_once()
