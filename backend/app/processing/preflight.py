"""PDF preflight classification and post-extraction quality gates.

The old pipeline decided between the ``fast`` and ``hi_res`` Unstructured
strategies by counting total extracted characters (< 50 -> hi_res).  That is
unreliable: a noisy scan can contain > 50 junk characters, and a legitimate
sparse text PDF can be needlessly pushed into OCR/layout analysis.

This module replaces that heuristic with a single preflight classifier before
Unstructured runs:

* **pdf-inspector** (Firecrawl's Rust classifier, used by AnyDoc/Fire-PDF)
  samples PDF content streams (``Tj``/``TJ`` text operators, ``Do`` image
  operators) and font encodings in ~10-50ms, returning a ``text_based`` /
  ``scanned`` / ``image_based`` / ``mixed`` type, a confidence score, and
  per-page OCR routing.
* A minimal PyMuPDF check runs first because pdf-inspector's classifier does
  not flag encrypted files; ``needs_pass`` is authoritative and cheap.

Classification routes to ``fast`` (text-based), ``hi_res`` (scanned,
image-based, or mixed), or a terminal error (encrypted/corrupt).  After
extraction, quality gates check per-page usable output, printable character
ratio, and suspicious repeated text, and can trigger a ``hi_res`` retry when
the ``fast`` pass is insufficient.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

log = logging.getLogger(__name__)

DocClass = Literal["text", "scanned", "mixed"]
Strategy = Literal["fast", "hi_res"]

#: A text element needs at least this many printable characters to count as
#: usable output for the quality gate.
MIN_TEXT_CHARS = 40


class PreflightError(Exception):
    """Terminal preflight failure (corrupt, encrypted, or unsupported PDF)."""

    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class DocumentPreflight:
    classification: DocClass
    route: Strategy
    confidence: str
    num_pages: int
    encrypted: bool = False
    corrupt: bool = False
    forced_strategy: str | None = None
    classifier: str = "pdf-inspector"
    ocr_pages: list[int] = field(default_factory=list)  # 0-indexed (pdf-inspector)
    limits_exceeded: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_pdf(pdf_file: Path) -> DocumentPreflight:
    """Classify a PDF with pdf-inspector and choose an extraction route.

    Raises :class:`PreflightError` for corrupt or encrypted files so the
    pipeline can mark the document with a precise terminal status instead of
    attempting extraction.
    """
    _check_encrypted_or_corrupt(pdf_file)
    result = _classify_with_pdf_inspector(pdf_file)
    result.limits_exceeded = _resource_limits(pdf_file)
    if result.limits_exceeded:
        raise PreflightError(
            "resource_limit",
            "Document exceeds configured limits: " + "; ".join(result.limits_exceeded),
        )
    return result


def _classify_with_pdf_inspector(pdf_file: Path) -> DocumentPreflight:
    """Run pdf-inspector and map its result onto our routing model."""
    import pdf_inspector

    forced = _forced_strategy()
    try:
        result = pdf_inspector.classify_pdf(str(pdf_file))
    except Exception as exc:
        raise PreflightError(
            "invalid", f"pdf-inspector could not classify the PDF: {exc}"
        ) from exc

    pdf_type = str(getattr(result, "pdf_type", "") or "").lower()
    type_map: dict[str, DocClass] = {
        "text_based": "text",
        "scanned": "scanned",
        "image_based": "scanned",
        "mixed": "mixed",
    }
    classification = type_map.get(pdf_type, "mixed")
    confidence = float(getattr(result, "confidence", 0.0) or 0.0)
    num_pages = int(getattr(result, "page_count", 0) or 0)
    ocr_pages = [int(p) for p in (getattr(result, "pages_needing_ocr", None) or [])]

    if forced:
        route: Strategy = "hi_res" if forced == "hi_res" else "fast"
    elif classification == "text":
        route = "fast"
    else:
        route = "hi_res"

    return DocumentPreflight(
        classification=classification,
        route=route,
        confidence=_confidence_label(confidence),
        num_pages=num_pages,
        forced_strategy=forced,
        classifier="pdf-inspector",
        ocr_pages=ocr_pages,
    )


def _check_encrypted_or_corrupt(pdf_file: Path) -> None:
    """Verify the PDF opens and is not password-protected.

    pdf-inspector's classifier reads the document structure without
    decrypting content streams, so it does not detect encryption on its own.
    PyMuPDF's ``needs_pass`` is authoritative and cheap, so it runs first.
    """
    import fitz

    try:
        doc = fitz.open(str(pdf_file))
    except Exception as exc:
        raise PreflightError(
            "invalid", f"Could not open PDF for preflight inspection: {exc}"
        ) from exc
    try:
        if doc.needs_pass:
            raise PreflightError(
                "encrypted", "PDF is encrypted; decryption is not supported"
            )
        if doc.is_encrypted:
            log.warning(
                "PDF %s reports encrypted metadata but needs no password", pdf_file
            )
    finally:
        doc.close()


def _confidence_label(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def _forced_strategy() -> str | None:
    import os

    value = os.getenv("UNSTRUCTURED_STRATEGY", "").strip().lower()
    return value or None


def _resource_limits(pdf_file: Path) -> list[str]:
    """Check page, decompressed-size, and image-count caps."""
    from app.processing.validation import inspect_resource_limits

    try:
        inspection = inspect_resource_limits(pdf_file)
    except Exception as exc:
        log.warning("resource-limit inspection failed for %s: %s", pdf_file, exc)
        return []
    return list(inspection.limits_exceeded)


def _printable_ratio(text: str) -> float:
    if not text:
        return 1.0
    printable = sum(ch.isprintable() for ch in text)
    return printable / len(text)


def _has_suspicious_repeats(text: str) -> bool:
    """Flag OCR/garbled output with pathological repetition.

    Covers long runs of a single character (``IIIIIIII``), repeated short
    n-grams, and runs of the same word separated by whitespace.
    """
    if not text.strip():
        return False
    for run in re.findall(r"(.)\1{9,}", text):
        if run.strip() and run != " ":
            return True
    stripped = re.sub(r"\s+", "", text)
    if len(stripped) >= 8 and len(set(stripped)) <= 2:
        return True
    words = re.findall(r"\b\w{3,}\b", text)
    if not words:
        return False
    counted = Counter(words)
    _word, count = counted.most_common(1)[0]
    return len(words) >= 12 and count / len(words) >= 0.5


def _text_quality(text: str) -> dict[str, Any]:
    stripped = "".join(ch for ch in text if ch.isprintable())
    suspicious = _has_suspicious_repeats(text)
    return {
        "chars": len(text),
        "printable_chars": len(stripped),
        "printable_ratio": _printable_ratio(text),
        "suspicious_repeats": suspicious,
    }


def quality_gate(
    elements: list[Any],
    expected_pages: int,
    *,
    classified_route: Strategy,
) -> list[str]:
    """Check extracted elements for usable output; return warnings.

    Warnings are returned (not raised) so the caller can decide whether to
    retry with ``hi_res``, keep the result as partial, or mark an error.
    """
    warnings: list[str] = []

    text_pages: set[int] = set()
    image_pages: set[int] = set()
    total_text = 0
    total_suspicious = 0

    for el in elements:
        meta = getattr(el, "metadata", None)
        page = int(getattr(meta, "page_number", None) or 1)
        text = str(getattr(el, "text", "") or "")
        category = str(getattr(el, "category", "") or type(el).__name__)

        if text:
            total_text += len(text)
            quality = _text_quality(text)
            if quality["suspicious_repeats"]:
                total_suspicious += 1
            if quality["chars"] >= MIN_TEXT_CHARS and quality["printable_ratio"] >= 0.9:
                text_pages.add(page)
        if category in ("Image", "Figure", "Table") or hasattr(meta, "image_path"):
            image_pages.add(page)

    if expected_pages > 0 and not text_pages and not image_pages:
        warnings.append(
            "Extraction produced no usable text or images on any page "
            f"(expected {expected_pages} pages)."
        )
        return warnings

    missing = expected_pages - len(text_pages | image_pages)
    if missing > 0:
        warnings.append(
            f"{missing} of {expected_pages} pages had no usable text or image output."
        )

    if total_text > 0 and total_suspicious / max(1, len(elements)) > 0.25:
        warnings.append(
            "A large share of extracted text looks garbled or suspiciously "
            "repeated; consider OCR review."
        )

    if total_text == 0 and image_pages:
        warnings.append(
            "Only images were extracted (no text). The document likely " "needs OCR."
        )

    if classified_route == "hi_res" and not text_pages and image_pages:
        warnings.append(
            "OCR/layout analysis completed but did not produce text output."
        )

    return warnings
