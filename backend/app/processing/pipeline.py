from __future__ import annotations

import asyncio
import logging
import traceback

from app import store
from app.processing import (
    chunking,
    embeddings,
    images,
    metadata,
    structure,
    tables,
    tree,
    vectorstore,
)
from app.processing.structure import Section

log = logging.getLogger(__name__)


_background_tasks: set[asyncio.Task[None]] = set()


def spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def process_document(doc_id: str) -> None:
    try:
        status = store.get_status(doc_id)
        if status is None:
            log.error("process_document: unknown doc_id %s", doc_id)
            return

        pdf = store.pdf_path(doc_id)

        store.update_status(
            doc_id,
            status="extracting",
            stage="parsing document structure",
            progress=0.05,
        )
        root, elements, num_pages, part_warnings = await asyncio.to_thread(
            structure.partition, pdf
        )
        store.update_status(
            doc_id,
            num_pages=num_pages,
            progress=0.25,
            warnings=part_warnings or None,
        )

        store.update_status(
            doc_id, status="tables", stage="extracting tables", progress=0.35
        )
        await tables.enrich_tables(pdf, elements)

        store.update_status(
            doc_id, status="images", stage="captioning figures", progress=0.55
        )
        images_dir = store.images_dir(doc_id)
        await images.enrich_images(pdf, images_dir, elements, root, len(elements))

        store.update_status(doc_id, stage="writing tree", progress=0.70)
        tree_json = tree.serialize(
            root, document_id=doc_id, filename=status.filename, num_pages=num_pages
        )
        store.save_tree(doc_id, tree_json)

        store.update_status(
            doc_id, status="embedding", stage="chunking and embedding", progress=0.85
        )
        chunks = chunking.build_chunks(root, doc_id)
        if chunks:
            await vectorstore.ensure_collection()
            vectors = await embeddings.embed_texts(
                [c.text_for_embedding for c in chunks]
            )
            await vectorstore.upsert_chunks(chunks, vectors)

        store.update_status(doc_id, status="ready", stage="ready", progress=1.0)

        spawn_background(enrich_in_background(doc_id, root, status.filename, num_pages))

    except Exception as e:
        log.exception("process_document failed for %s", doc_id)
        store.update_status(
            doc_id,
            status="error",
            stage="error",
            progress=1.0,
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}",
        )


async def enrich_in_background(
    doc_id: str, root: Section, filename: str, num_pages: int
) -> None:
    try:
        log.info("background enrichment start for %s", doc_id)
        sections_index, doc_meta = await metadata.build_enrichment(
            root,
            document_id=doc_id,
            filename=filename,
            num_pages=num_pages,
        )
        store.save_sections_index(doc_id, sections_index)
        store.save_document_meta(doc_id, doc_meta)
        log.info(
            "background enrichment done for %s (%d sections)",
            doc_id,
            len(sections_index),
        )
    except Exception:
        log.exception("background enrichment failed for %s", doc_id)
