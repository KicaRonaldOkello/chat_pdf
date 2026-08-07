"""PDF input validation and resource-limit inspection.

Catches bad input before it reaches the expensive extraction pipeline:

* magic-byte verification (a ``.pdf`` suffix alone is not enough);
* structural readability via pypdf;
* page, decompressed-stream, and image-count caps against settings.
"""

from __future__ import annotations

import contextlib
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.settings import settings

log = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"


@dataclass
class PdfInspection:
    """Structural facts about a PDF, used for upload validation and limits."""

    is_pdf: bool
    readable: bool
    num_pages: int = 0
    decompressed_bytes: int = 0
    image_count: int = 0
    limits_exceeded: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "is_pdf": self.is_pdf,
            "readable": self.readable,
            "num_pages": self.num_pages,
            "decompressed_bytes": self.decompressed_bytes,
            "image_count": self.image_count,
            "limits_exceeded": self.limits_exceeded,
        }


def validate_pdf_bytes(data: bytes | Path) -> PdfInspection:
    """Validate PDF magic bytes and structural readability."""
    if isinstance(data, Path):
        try:
            with data.open("rb") as fh:
                header = fh.read(len(PDF_MAGIC))
        except OSError as exc:
            log.info("upload validation: cannot read %s (%s)", data, exc)
            return PdfInspection(is_pdf=False, readable=False)
        raw: bytes | Path = data
    else:
        header = data[: len(PDF_MAGIC)]
        raw = data
    if not header.startswith(PDF_MAGIC):
        return PdfInspection(is_pdf=False, readable=False)

    inspection = PdfInspection(is_pdf=True, readable=False)
    try:
        with _open_reader(raw) as reader:
            inspection.readable = True
            inspection.num_pages = len(reader.pages)
    except Exception as exc:
        log.info("upload validation: PDF bytes unreadable (%s)", exc)
    return inspection


def inspect_resource_limits(data: bytes | Path) -> PdfInspection:
    """Return structural facts and any exceeded resource caps."""
    inspection = validate_pdf_bytes(data)
    if not inspection.readable:
        return inspection

    try:
        with _open_reader(data) as reader:
            inspection.num_pages = len(reader.pages)
            inspection.decompressed_bytes = _decompressed_stream_bytes(reader)
            inspection.image_count = sum(len(page.images) for page in reader.pages)
        if inspection.num_pages > settings.max_pdf_pages:
            inspection.limits_exceeded.append(
                f"pages={inspection.num_pages} > {settings.max_pdf_pages}"
            )
        if inspection.decompressed_bytes > settings.max_pdf_decompressed_bytes:
            inspection.limits_exceeded.append(
                "decompressed_bytes="
                f"{inspection.decompressed_bytes} > "
                f"{settings.max_pdf_decompressed_bytes}"
            )
        if inspection.image_count > settings.max_pdf_images:
            inspection.limits_exceeded.append(
                f"images={inspection.image_count} > {settings.max_pdf_images}"
            )
    except Exception as exc:
        log.warning("resource-limit inspection failed: %s", exc)
    return inspection


def _open_reader(data: bytes | Path):
    from pypdf import PdfReader

    if isinstance(data, Path):
        return PdfReader(str(data), strict=False)
    return PdfReader(io.BytesIO(data), strict=False)


def _decompressed_stream_bytes(reader) -> int:
    """Sum decoded lengths of all stream objects in the document.

    This walks every object in the cross-reference table, so it is a
    decompression-bomb check in the same spirit as pdf-inspector's
    ``ResourceLimit`` guard.  stderr is suppressed because pypdf logs
    "object not defined" noise for sparse xref tables.
    """
    total = 0
    max_id = 1
    try:
        size = reader.trailer.get("/Size")
        if size is not None:
            max_id = int(size)
    except Exception:
        max_id = 1_000_000
    with contextlib.redirect_stderr(io.StringIO()):
        for obj_id in range(1, min(max_id + 1, 2_000_000)):
            try:
                obj = reader.get_object(obj_id)
            except Exception:
                continue
            if hasattr(obj, "get_data"):
                total += len(obj.get_data())
            if total > settings.max_pdf_decompressed_bytes:
                break
    return total
