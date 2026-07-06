"""Abstract base class for file storage backends (S3, local filesystem, etc.)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class StorageBackend(ABC):
    """Interface that every storage backend must implement.

    Methods mirror the original ``s3_storage`` module's public API so that
    swapping backends requires zero changes at call sites.
    """

    # ── PDF source files ─────────────────────────────────────────────────

    @abstractmethod
    def put_source_pdf_bytes(
        self, doc_id: str, data: bytes, content_type: str = "application/pdf"
    ) -> None:
        """Persist the raw uploaded PDF for *doc_id*."""

    @abstractmethod
    def get_source_pdf_bytes(self, doc_id: str) -> bytes:
        """Return the full PDF bytes.  Raise ``FileNotFoundError`` if missing."""

    @abstractmethod
    def get_source_pdf_streaming(self, doc_id: str) -> Iterator[bytes]:
        """Yield the PDF in chunks (for HTTP streaming responses)."""

    # ── Image files ──────────────────────────────────────────────────────

    @abstractmethod
    def put_image_bytes(
        self,
        doc_id: str,
        filename: str,
        data: bytes,
        content_type: str = "image/png",
    ) -> str:
        """Store an image; return a key/path that can be recorded in the DB."""

    # ── Cleanup ──────────────────────────────────────────────────────────

    @abstractmethod
    def delete_all_for_document(self, doc_id: str) -> None:
        """Remove every stored artefact for *doc_id* (PDF, images, etc.)."""

    # ── Table Markdown ────────────────────────────────────────────────────

    @abstractmethod
    def put_table_markdown(self, doc_id: str, table_index: int, markdown: str) -> str:
        """Persist full table markdown for large tables; return a retrieval key."""

    @abstractmethod
    def get_table_markdown(self, doc_id: str, key: str) -> str:
        """Read back full table markdown from its retrieval key."""

    # ── Debug / Local Inspection ─────────────────────────────────────────

    @abstractmethod
    def put_debug_json(self, doc_id: str, filename: str, data: Any) -> None:
        """Store debug JSON data for inspection (e.g. tree, chunks, metadata)."""
