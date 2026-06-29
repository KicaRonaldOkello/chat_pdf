"""Local-filesystem storage backend for development.

Files are stored under ``DOCUMENTS_DIR / <doc_id> / ...``:

    data/documents/<doc_id>/source.pdf
    data/documents/<doc_id>/images/<filename>
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Iterator

from app.config import DOCUMENTS_DIR
from app.storage.base import StorageBackend

log = logging.getLogger(__name__)

_CHUNK_SIZE = 65_536  # 64 KiB — matches the S3 streaming chunk size


class LocalStorageBackend(StorageBackend):
    """Read/write files on the local filesystem under ``DOCUMENTS_DIR``."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or DOCUMENTS_DIR
        self._root.mkdir(parents=True, exist_ok=True)

    # ── helpers ──────────────────────────────────────────────────────────

    def _doc_dir(self, doc_id: str) -> Path:
        return self._root / doc_id

    def _source_path(self, doc_id: str) -> Path:
        return self._doc_dir(doc_id) / "source.pdf"

    def _image_path(self, doc_id: str, filename: str) -> Path:
        return self._doc_dir(doc_id) / "images" / filename.lstrip("/")

    # ── PDF source files ─────────────────────────────────────────────────

    def put_source_pdf_bytes(
        self, doc_id: str, data: bytes, content_type: str = "application/pdf"
    ) -> None:
        path = self._source_path(doc_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        log.debug("local: wrote %d bytes → %s", len(data), path)

    def get_source_pdf_bytes(self, doc_id: str) -> bytes:
        path = self._source_path(doc_id)
        if not path.exists():
            raise FileNotFoundError(f"local://{path}")
        return path.read_bytes()

    def get_source_pdf_streaming(self, doc_id: str) -> Iterator[bytes]:
        path = self._source_path(doc_id)
        if not path.exists():
            raise FileNotFoundError(f"local://{path}")
        with open(path, "rb") as f:
            while chunk := f.read(_CHUNK_SIZE):
                yield chunk

    # ── Image files ──────────────────────────────────────────────────────

    def put_image_bytes(
        self,
        doc_id: str,
        filename: str,
        data: bytes,
        content_type: str = "image/png",
    ) -> str:
        path = self._image_path(doc_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        # Return a relative key similar to S3 convention
        return str(path.relative_to(self._root))

    # ── Cleanup ──────────────────────────────────────────────────────────

    def delete_all_for_document(self, doc_id: str) -> None:
        doc_dir = self._doc_dir(doc_id)
        if doc_dir.exists():
            shutil.rmtree(doc_dir, ignore_errors=True)
            log.debug("local: deleted %s", doc_dir)

    # ── Table Markdown ────────────────────────────────────────────────────

    def put_table_markdown(self, doc_id: str, table_index: int, markdown: str) -> str:
        path = self._doc_dir(doc_id) / "tables" / f"table_{table_index}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        log.debug("local: wrote table markdown → %s", path)
        return f"tables/table_{table_index}.md"

    def get_table_markdown(self, doc_id: str, key: str) -> str:
        path = self._doc_dir(doc_id) / key
        if not path.exists():
            raise FileNotFoundError(f"local://{path}")
        return path.read_text(encoding="utf-8")

    # ── Debug / Local Inspection ─────────────────────────────────────────

    def put_debug_json(self, doc_id: str, filename: str, data: Any) -> None:
        path = self._doc_dir(doc_id) / f"{filename}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        log.debug("local: wrote debug JSON to %s", path)
