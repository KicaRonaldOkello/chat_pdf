from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass

from app import document_data
from app.db.repositories.document_state import DocumentStatus
from app.processing import (
    chunking,
    concurrency,
    embeddings,
    images,
    metadata,
    preflight,
    structure,
    tables,
    tree,
    vectorstore,
)
from app.processing.preflight import PreflightError
from app.processing.structure import Section
from app.settings import settings
from app.storage import get_storage

log = logging.getLogger(__name__)

RETRYABLE_STATUSES = frozenset({"parser_failure", "resource_limit"})

# Fire-and-forget enrichment tasks, tracked so they are not garbage-collected.
_enrichment_tasks: set[asyncio.Task[None]] = set()


def _spawn_enrichment(
    doc_id: str, root: Section, filename: str, num_pages: int
) -> None:
    """Run metadata enrichment off the processing path; failures are non-fatal."""
    task = asyncio.create_task(enrich_in_background(doc_id, root, filename, num_pages))
    _enrichment_tasks.add(task)
    task.add_done_callback(_enrichment_tasks.discard)


@dataclass
class RunOutcome:
    """Result of one processing attempt, for the worker's retry decision."""

    status: str
    retryable: bool
    error: str | None = None


async def process_document(doc_id: str, run_attempt: int = 1) -> RunOutcome:
    # Captured during the main pipeline; consumed by enrichment after the
    # document is marked ready.
    _enrich_root: Section | None = None
    _enrich_filename: str = ""
    _enrich_num_pages: int = 0
    final_status = "parser_failure"
    final_error: str | None = None

    async with document_data.document_db_session() as (session, repo):
        status = await repo.get_status(doc_id)
        if status is None:
            log.warning("process_document: unknown doc_id %s", doc_id)
            return RunOutcome(status="unknown", retryable=False)

        _enrich_filename = status.filename

        try:
            pdf = await asyncio.to_thread(
                document_data.pull_source_pdf_to_tempfile, doc_id
            )
        except Exception as e:
            log.exception(
                "process_document: could not load source PDF for %s: %s", doc_id, e
            )
            final_status = "parser_failure"
            final_error = str(e)
            try:
                await repo.set_status(
                    doc_id,
                    DocumentStatus(
                        status="parser_failure",
                        stage="failed to load source PDF",
                        progress=0.0,
                        filename=status.filename,
                        error=str(e),
                    ),
                )
                await session.commit()
            except Exception:  # pragma: no cover
                pass
            return RunOutcome(
                status=final_status,
                retryable=final_status in RETRYABLE_STATUSES,
                error=final_error,
            )

        try:
            async with asyncio.timeout(settings.processing_timeout_seconds):
                await repo.update_status(
                    doc_id,
                    status="extracting",
                    stage=f"classifying document (attempt {run_attempt})",
                    progress=0.05,
                )
                await session.commit()
                async with concurrency.parse_semaphore():
                    preflight_result = await asyncio.to_thread(
                        preflight.classify_pdf, pdf
                    )
                get_storage().put_debug_json(
                    doc_id, "preflight", preflight_result.to_dict()
                )
                await repo.update_status(
                    doc_id,
                    stage=f"parsing document structure via {preflight_result.route}",
                    progress=0.25,
                )
                await session.commit()

                loop = asyncio.get_running_loop()

                def _report_ocr(
                    stage: str, progress: float, _extra: dict[str, Any]
                ) -> None:
                    """Bridge OCR progress from the partition worker thread to the
                    async status row without blocking the thread."""

                    async def _write() -> None:
                        try:
                            # Short-lived session per write: the pipeline's own
                            # session must never be shared with tasks scheduled
                            # from another thread.
                            async with document_data.document_db_session() as (
                                write_session,
                                write_repo,
                            ):
                                await write_repo.update_status(
                                    doc_id,
                                    status="extracting",
                                    stage=stage,
                                    progress=progress,
                                )
                                await write_session.commit()
                        except Exception:
                            log.exception(
                                "failed to report OCR progress for %s", doc_id
                            )

                    asyncio.run_coroutine_threadsafe(_write(), loop)

                async with concurrency.parse_semaphore():
                    root, elements, num_pages, part_warnings = await asyncio.to_thread(
                        structure.partition,
                        pdf,
                        preflight=preflight_result,
                        on_stage=_report_ocr,
                    )
                _enrich_root = root
                _enrich_num_pages = num_pages
                await repo.update_status(
                    doc_id,
                    num_pages=num_pages,
                    warnings=part_warnings or None,
                )
                await session.commit()

                await repo.update_status(
                    doc_id, status="tables", stage="extracting tables", progress=0.35
                )
                await session.commit()
                async with concurrency.parse_semaphore():
                    table_diag = await tables.enrich_tables(pdf, root, elements)
                get_storage().put_debug_json(
                    doc_id, "table_diagnostics", table_diag.to_dict()
                )
                if table_diag.errors:
                    part_warnings = [
                        f"table extraction: {err}" for err in table_diag.errors
                    ] + (part_warnings or [])
                await repo.update_status(doc_id, warnings=part_warnings or None)
                await session.commit()

                await repo.update_status(
                    doc_id, status="images", stage="extracting figures", progress=0.55
                )
                await session.commit()
                await images.enrich_images(pdf, doc_id, elements, root, len(elements))

                await repo.update_status(doc_id, stage="writing tree", progress=0.70)
                await session.commit()
                tree_json = tree.serialize(
                    root,
                    document_id=doc_id,
                    filename=status.filename,
                    num_pages=num_pages,
                )
                await repo.save_tree(doc_id, tree_json)
                await session.commit()
                get_storage().put_debug_json(doc_id, "structure_tree", tree_json)

                await repo.update_status(
                    doc_id,
                    status="embedding",
                    stage="chunking and embedding",
                    progress=0.85,
                )
                await session.commit()
                chunks = chunking.build_chunks(root, doc_id)
                get_storage().put_debug_json(
                    doc_id,
                    "chunks",
                    [
                        {
                            "chunk_id": c.chunk_id,
                            "type": c.type,
                            "page": c.page,
                            "section_path": c.section_path,
                            "text_for_embedding": c.text_for_embedding,
                            "display_text": c.display_text,
                            "bbox": c.bbox,
                            "page_size": c.page_size,
                            "extra": c.extra,
                        }
                        for c in chunks
                    ],
                )
                if chunks:
                    await vectorstore.delete_doc(doc_id, session=session)
                    async with concurrency.embedding_semaphore():
                        vectors = await embeddings.embed_texts(
                            [c.text_for_embedding for c in chunks]
                        )
                    await vectorstore.upsert_chunks(chunks, vectors, session=session)

                final_status = "partial" if part_warnings else "ready"
                await repo.update_status(
                    doc_id, status=final_status, stage="ready", progress=1.0
                )
                await session.commit()
        except TimeoutError:
            log.error("process_document timed out for %s", doc_id)
            final_status = "resource_limit"
            final_error = (
                f"Processing timed out after {settings.processing_timeout_seconds}s"
            )
            try:
                await repo.update_status(
                    doc_id,
                    status="resource_limit",
                    stage=(
                        f"processing exceeded "
                        f"{settings.processing_timeout_seconds}s limit"
                    ),
                    progress=1.0,
                    error=final_error,
                )
                await session.commit()
            except Exception:  # pragma: no cover
                pass
        except PreflightError as e:
            log.warning("preflight rejected %s: [%s] %s", doc_id, e.status, e.message)
            final_status = e.status
            final_error = f"{type(e).__name__}: {e}"
            try:
                await repo.update_status(
                    doc_id,
                    status=e.status,
                    stage=e.message,
                    progress=1.0,
                    error=final_error,
                )
                await session.commit()
            except Exception:  # pragma: no cover
                pass
        except Exception as e:
            log.exception("process_document failed for %s", doc_id)
            final_status = "parser_failure"
            final_error = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}"
            try:
                await repo.update_status(
                    doc_id,
                    status="parser_failure",
                    stage="parser failure",
                    progress=1.0,
                    error=final_error,
                )
                await session.commit()
            except Exception:  # pragma: no cover
                pass
        finally:
            await asyncio.to_thread(document_data.release_source_temp_path, pdf)

    outcome = RunOutcome(
        status=final_status,
        retryable=final_status in RETRYABLE_STATUSES,
        error=final_error,
    )

    # Enrichment runs *after* the document is ready so that chunk retrieval
    # works immediately.  Failures here are non-fatal — the document is
    # already queryable; only metadata quality is degraded.  It is spawned
    # rather than awaited so a slow/failing LLM provider can never block the
    # worker from claiming new documents.
    if _enrich_root is not None and final_status in ("ready", "partial"):
        _spawn_enrichment(doc_id, _enrich_root, _enrich_filename, _enrich_num_pages)
    return outcome


async def enrich_in_background(
    doc_id: str, root: Section, filename: str, num_pages: int
) -> None:
    try:
        log.info("background enrichment start for %s", doc_id)
        sections_index, doc_meta = await asyncio.wait_for(
            metadata.build_enrichment(
                root,
                document_id=doc_id,
                filename=filename,
                num_pages=num_pages,
            ),
            timeout=settings.metadata_openrouter_enrichment_deadline_seconds,
        )
        await document_data.save_sections_index(doc_id, sections_index)
        await document_data.save_document_meta(doc_id, doc_meta)
        get_storage().put_debug_json(doc_id, "sections_index", sections_index)
        get_storage().put_debug_json(doc_id, "metadata", doc_meta)
        log.info(
            "background enrichment done for %s (%d sections)",
            doc_id,
            len(sections_index),
        )
    except TimeoutError:
        log.warning(
            "background enrichment timed out for %s after %.0fs "
            "(document is still ready)",
            doc_id,
            settings.metadata_openrouter_enrichment_deadline_seconds,
        )
    except Exception:
        log.exception("background enrichment failed for %s", doc_id)
