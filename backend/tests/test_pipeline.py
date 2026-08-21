"""process_document wiring: mock filesystem, DB session, structure, and vector I/O."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from app.db.repositories.document_state import DocumentStatus
from app.processing.pipeline import enrich_in_background, process_document
from app.processing.preflight import DocumentPreflight, PreflightError
from app.settings import settings
from app.processing.structure import ElementRef, Section
from app.processing.tables import TableDiagnostics


async def _noop_enrich(*args, **kwargs) -> None:
    """Stand-in for enrich_in_background — runs inline, does nothing."""
    return None


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
            "app.processing.pipeline.enrich_in_background",
            new_callable=AsyncMock,
        ) as enrich,
    ):
        outcome = await process_document("missing-id")

    assert outcome.status == "unknown"
    assert outcome.retryable is False
    pull.assert_not_called()
    release.assert_not_called()
    enrich.assert_not_awaited()


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
            "app.processing.pipeline.enrich_in_background",
            new_callable=AsyncMock,
        ) as enrich,
    ):
        await process_document("doc-1")

    repo.set_status.assert_awaited()
    args, _kw = repo.set_status.call_args
    assert args[0] == "doc-1"
    st: DocumentStatus = args[1]
    assert st.status == "parser_failure"
    assert "load source PDF" in st.stage
    assert st.error is not None
    session.commit.assert_awaited()
    release.assert_not_called()
    enrich.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_document_happy_path_ready_and_spawns_enrichment() -> None:
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
    preflight = DocumentPreflight(
        classification="text",
        route="fast",
        confidence="high",
        num_pages=3,
    )

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
        patch(
            "app.processing.pipeline.structure.partition",
            return_value=(root, [], 3, []),
        ),
        patch("app.processing.pipeline.tables.enrich_tables", new_callable=AsyncMock),
        patch("app.processing.pipeline.images.enrich_images", new_callable=AsyncMock),
        patch("app.processing.pipeline.chunking.build_chunks", return_value=[]),
        patch(
            "app.processing.pipeline.vectorstore.ensure_collection",
            new_callable=AsyncMock,
        ),
        patch("app.processing.pipeline.embeddings.embed_texts", new_callable=AsyncMock),
        patch(
            "app.processing.pipeline.vectorstore.upsert_chunks", new_callable=AsyncMock
        ) as upsert,
        patch(
            "app.processing.pipeline.preflight.classify_pdf",
            return_value=preflight,
        ) as classify,
        patch(
            "app.processing.pipeline._spawn_enrichment",
            new_callable=MagicMock,
        ) as spawn_enrich,
    ):
        outcome = await process_document("doc-42")

    assert outcome.status == "ready"
    assert outcome.retryable is False
    release.assert_called_once_with(pdf_path)
    upsert.assert_not_awaited()
    classify.assert_called_once_with(pdf_path)
    repo.save_tree.assert_awaited_once_with("doc-42", ANY)
    final = repo.update_status.await_args_list[-1]
    assert final.args[0] == "doc-42"
    assert final.kwargs.get("status") == "ready"
    assert final.kwargs.get("progress") == 1.0
    spawn_enrich.assert_called_once_with("doc-42", root, "paper.pdf", 3)


@pytest.mark.asyncio
async def test_enrich_in_background_times_out_gracefully(monkeypatch) -> None:
    async def _never(*_args, **_kwargs):
        await asyncio.sleep(60)
        return [], {}

    monkeypatch.setattr(
        settings, "metadata_openrouter_enrichment_deadline_seconds", 0.05
    )
    with (
        patch(
            "app.processing.pipeline.metadata.build_enrichment",
            side_effect=_never,
        ),
        patch(
            "app.processing.pipeline.document_data.save_sections_index",
            new_callable=AsyncMock,
        ) as save_index,
    ):
        await enrich_in_background("doc-timeout", _minimal_root(), "f.pdf", 3)

    save_index.assert_not_awaited()  # timed out before saving anything


@pytest.mark.asyncio
async def test_process_document_records_table_diagnostics_and_warnings() -> None:
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

    preflight = DocumentPreflight(
        classification="text",
        route="fast",
        confidence="high",
        num_pages=3,
    )
    table_diag = TableDiagnostics(
        total_pages=3, errors=["lattice extraction failed: x"]
    )
    storage = MagicMock()

    with (
        patch("app.processing.pipeline.document_data.document_db_session", cm),
        patch(
            "app.processing.pipeline.document_data.pull_source_pdf_to_tempfile",
            return_value=Path("/tmp/tables.pdf"),
        ),
        patch(
            "app.processing.pipeline.document_data.release_source_temp_path",
            new_callable=MagicMock,
        ),
        patch(
            "app.processing.pipeline.preflight.classify_pdf",
            return_value=preflight,
        ),
        patch(
            "app.processing.pipeline.structure.partition",
            return_value=(root, [], 3, []),
        ),
        patch(
            "app.processing.pipeline.tables.enrich_tables",
            new_callable=AsyncMock,
            return_value=table_diag,
        ),
        patch("app.processing.pipeline.images.enrich_images", new_callable=AsyncMock),
        patch("app.processing.pipeline.chunking.build_chunks", return_value=[]),
        patch("app.processing.pipeline.get_storage", return_value=storage),
        patch(
            "app.processing.pipeline._spawn_enrichment",
            new_callable=MagicMock,
        ),
    ):
        await process_document("doc-tables")

    storage.put_debug_json.assert_any_call(
        "doc-tables", "table_diagnostics", table_diag.to_dict()
    )
    # The table error also flows into the processing warnings payload.
    assert any(
        "table extraction: lattice extraction failed" in str(call)
        for call in repo.update_status.await_args_list
    )


@pytest.mark.asyncio
async def test_process_document_encrypted_preflight_marks_terminal_status() -> None:
    repo = MagicMock()
    repo.get_status = AsyncMock(
        return_value=DocumentStatus(
            status="queued",
            stage="queued",
            progress=0.0,
            filename="secret.pdf",
        )
    )
    repo.update_status = AsyncMock()
    cm, session = _fake_db_session(repo)
    session.commit = AsyncMock()

    with (
        patch("app.processing.pipeline.document_data.document_db_session", cm),
        patch(
            "app.processing.pipeline.document_data.pull_source_pdf_to_tempfile",
            return_value=Path("/tmp/secret.pdf"),
        ),
        patch(
            "app.processing.pipeline.document_data.release_source_temp_path",
            new_callable=MagicMock,
        ),
        patch(
            "app.processing.pipeline.preflight.classify_pdf",
            side_effect=PreflightError(
                "encrypted", "PDF is encrypted; decryption is not supported"
            ),
        ),
        patch(
            "app.processing.pipeline.enrich_in_background",
            new_callable=AsyncMock,
        ) as enrich,
    ):
        await process_document("doc-secret")

    final = repo.update_status.await_args_list[-1]
    assert final.args[0] == "doc-secret"
    assert final.kwargs.get("status") == "encrypted"
    assert "encrypted" in final.kwargs.get("stage", "").lower()
    enrich.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_document_partial_when_warnings_present() -> None:
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

    preflight = DocumentPreflight(
        classification="text",
        route="fast",
        confidence="high",
        num_pages=3,
    )
    warnings = ["1 of 3 pages had no usable text or image output."]

    with (
        patch("app.processing.pipeline.document_data.document_db_session", cm),
        patch(
            "app.processing.pipeline.document_data.pull_source_pdf_to_tempfile",
            return_value=Path("/tmp/partial.pdf"),
        ),
        patch(
            "app.processing.pipeline.document_data.release_source_temp_path",
            new_callable=MagicMock,
        ),
        patch(
            "app.processing.pipeline.preflight.classify_pdf",
            return_value=preflight,
        ),
        patch(
            "app.processing.pipeline.structure.partition",
            return_value=(root, [], 3, warnings),
        ),
        patch("app.processing.pipeline.tables.enrich_tables", new_callable=AsyncMock),
        patch("app.processing.pipeline.images.enrich_images", new_callable=AsyncMock),
        patch("app.processing.pipeline.chunking.build_chunks", return_value=[]),
        patch(
            "app.processing.pipeline._spawn_enrichment",
            new_callable=MagicMock,
        ),
    ):
        await process_document("doc-partial")

    final = repo.update_status.await_args_list[-1]
    assert final.kwargs.get("status") == "partial"
    with_warnings = [
        call for call in repo.update_status.await_args_list if "warnings" in call.kwargs
    ]
    assert with_warnings and with_warnings[-1].kwargs["warnings"] == warnings


@pytest.mark.asyncio
async def test_process_document_resource_limit_rejection() -> None:
    repo = MagicMock()
    repo.get_status = AsyncMock(
        return_value=DocumentStatus(
            status="queued",
            stage="queued",
            progress=0.0,
            filename="huge.pdf",
        )
    )
    repo.update_status = AsyncMock()
    cm, session = _fake_db_session(repo)
    session.commit = AsyncMock()

    with (
        patch("app.processing.pipeline.document_data.document_db_session", cm),
        patch(
            "app.processing.pipeline.document_data.pull_source_pdf_to_tempfile",
            return_value=Path("/tmp/huge.pdf"),
        ),
        patch(
            "app.processing.pipeline.document_data.release_source_temp_path",
            new_callable=MagicMock,
        ),
        patch(
            "app.processing.pipeline.preflight.classify_pdf",
            side_effect=PreflightError(
                "resource_limit", "Document exceeds configured limits: pages=600"
            ),
        ),
        patch(
            "app.processing.pipeline.enrich_in_background",
            new_callable=AsyncMock,
        ) as enrich,
    ):
        await process_document("doc-huge")

    final = repo.update_status.await_args_list[-1]
    assert final.kwargs.get("status") == "resource_limit"
    assert "pages=600" in final.kwargs.get("stage", "")
    enrich.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_document_times_out_marks_resource_limit() -> None:
    from app.processing.pipeline import settings

    original_timeout = settings.processing_timeout_seconds
    settings.processing_timeout_seconds = 0.01
    repo = MagicMock()
    repo.get_status = AsyncMock(
        return_value=DocumentStatus(
            status="queued",
            stage="queued",
            progress=0.0,
            filename="slow.pdf",
        )
    )
    repo.update_status = AsyncMock()
    cm, session = _fake_db_session(repo)
    session.commit = AsyncMock()

    import time

    def _slow_classify(_path) -> DocumentPreflight:
        time.sleep(1)
        return DocumentPreflight(
            classification="text",
            route="fast",
            confidence="high",
            num_pages=1,
        )

    try:
        with (
            patch("app.processing.pipeline.document_data.document_db_session", cm),
            patch(
                "app.processing.pipeline.document_data.pull_source_pdf_to_tempfile",
                return_value=Path("/tmp/slow.pdf"),
            ),
            patch(
                "app.processing.pipeline.document_data.release_source_temp_path",
                new_callable=MagicMock,
            ),
            patch(
                "app.processing.pipeline.preflight.classify_pdf",
                side_effect=_slow_classify,
            ),
            patch(
                "app.processing.pipeline.enrich_in_background",
                new_callable=AsyncMock,
            ),
        ):
            await process_document("doc-slow")
    finally:
        settings.processing_timeout_seconds = original_timeout

    final = repo.update_status.await_args_list[-1]
    assert final.kwargs.get("status") == "resource_limit"
    assert "timed out" in (final.kwargs.get("error") or "").lower()
