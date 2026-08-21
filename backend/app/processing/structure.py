from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: Retry OCR when at least this fraction of pages is missing (proportional gate).
MIN_HIRES_RETRY_FRACTION = 0.10
#: Above this missing fraction, retry the whole document (page-targeted OCR
#: would reload models once per batch and be wasteful for mostly-empty docs).
FULL_DOC_HIRES_FRACTION = 0.50


@dataclass
class ElementRef:
    id: str
    type: str  # "text" | "table" | "image" | "formula"
    page: int
    text: str = ""
    bbox: list[float] | None = None  # [x0, y0, x1, y1] when available
    page_size: list[float] | None = None  # [width, height] of that coord system
    extra: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ElementRef:
        """Deserialize an ElementRef from its ``to_dict`` representation."""
        _KNOWN = {"id", "type", "page", "text", "bbox", "page_size"}
        extra = {k: v for k, v in data.items() if k not in _KNOWN}
        return ElementRef(
            id=str(data["id"]),
            type=str(data["type"]),
            page=int(data.get("page", 1)),
            text=str(data.get("text", "")),
            bbox=(
                [float(x) for x in data["bbox"]]
                if "bbox" in data and data["bbox"] is not None
                else None
            ),
            page_size=(
                [float(x) for x in data["page_size"]]
                if "page_size" in data and data["page_size"] is not None
                else None
            ),
            extra=extra,
        )


@dataclass
class Section:
    id: str
    title: str
    level: int
    path: str  # "Methods > Dataset"
    page_range: list[int]  # [first_page, last_page]
    elements: list[ElementRef] = field(default_factory=list)
    children: list[Section] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "level": self.level,
            "path": self.path,
            "page_range": self.page_range,
            "elements": [
                {
                    "id": e.id,
                    "type": e.type,
                    "page": e.page,
                    "text": e.text,
                    **({"bbox": e.bbox} if e.bbox else {}),
                    **({"page_size": e.page_size} if e.page_size else {}),
                    **e.extra,
                }
                for e in self.elements
            ],
            "children": [c.to_dict() for c in self.children],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Section:
        """Deserialize a Section from its ``to_dict`` representation."""
        return Section(
            id=str(data["id"]),
            title=str(data["title"]),
            level=int(data["level"]),
            path=str(data["path"]),
            page_range=[int(p) for p in data["page_range"]],
            elements=[ElementRef.from_dict(e) for e in data.get("elements", [])],
            children=[Section.from_dict(c) for c in data.get("children", [])],
        )


def el_category(el: Any) -> str:
    cat = getattr(el, "category", None)
    if cat:
        return str(cat)
    return type(el).__name__


def el_page(el: Any) -> int:
    meta = getattr(el, "metadata", None)
    page = getattr(meta, "page_number", None) if meta else None
    return int(page) if page else 1


def el_bbox(el: Any) -> list[float] | None:
    meta = getattr(el, "metadata", None)
    coords = getattr(meta, "coordinates", None) if meta else None
    if not coords:
        return None
    points = getattr(coords, "points", None)
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]


def el_page_size(el: Any) -> list[float] | None:
    meta = getattr(el, "metadata", None)
    coords = getattr(meta, "coordinates", None) if meta else None
    if not coords:
        return None
    system = getattr(coords, "system", None)
    if not system:
        return None
    w = getattr(system, "width", None)
    h = getattr(system, "height", None)
    if w is None or h is None:
        return None
    return [float(w), float(h)]


def el_text(el: Any) -> str:
    return str(getattr(el, "text", "") or "").strip()


TYPE_MAP = {
    "Table": "table",
    "Image": "image",
    "Figure": "image",
    "FigureCaption": "text",
    "Formula": "formula",
}


def to_element_ref(el: Any, idx: int) -> ElementRef | None:
    cat = el_category(el)
    if cat in ("Title", "Header", "SectionHeader"):
        return None
    if cat in ("PageBreak", "Footer", "Address"):
        return None
    etype = TYPE_MAP.get(cat, "text")
    text = el_text(el)
    if etype == "text" and not text:
        return None
    extra: dict[str, Any] = {}
    if etype == "table":
        meta = getattr(el, "metadata", None)
        html = getattr(meta, "text_as_html", None) if meta else None
        if html:
            extra["html"] = str(html)
    return ElementRef(
        id=f"el-{idx}",
        type=etype,
        page=el_page(el),
        text=text,
        bbox=el_bbox(el),
        page_size=el_page_size(el),
        extra=extra,
    )


def infer_level(el: Any) -> int:
    meta = getattr(el, "metadata", None)
    cat_depth = getattr(meta, "category_depth", None) if meta else None
    if isinstance(cat_depth, int) and cat_depth >= 0:
        return cat_depth + 1
    cat = el_category(el)
    if cat == "Title":
        return 1
    if cat in ("Header", "SectionHeader"):
        return 2
    return 1


def new_section(
    sid: str, title: str, level: int, page: int, parent_path: str
) -> Section:
    path = f"{parent_path} > {title}" if parent_path else title
    return Section(
        id=sid,
        title=title or "(untitled)",
        level=level,
        path=path,
        page_range=[page, page],
    )


def build_tree(elements: Iterable[Any]) -> tuple[Section, list[ElementRef], int]:
    root = Section(id="sec-root", title="(root)", level=0, path="", page_range=[1, 1])
    stack: list[Section] = [root]
    all_elements: list[ElementRef] = []
    max_page = 1
    sec_counter = 0
    el_counter = 0

    for el in elements:
        page = el_page(el)
        max_page = max(max_page, page)
        cat = el_category(el)

        if cat in ("Title", "Header", "SectionHeader"):
            level = max(1, infer_level(el))
            title = el_text(el)
            if not title:
                continue
            sec_counter += 1
            while len(stack) > 1 and stack[-1].level >= level:
                stack.pop()
            parent = stack[-1]
            section = new_section(
                sid=f"sec-{sec_counter}",
                title=title,
                level=level,
                page=page,
                parent_path=parent.path,
            )
            parent.children.append(section)
            stack.append(section)
            continue

        el_counter += 1
        ref = to_element_ref(el, el_counter)
        if ref is None:
            continue
        container = stack[-1]
        container.elements.append(ref)
        all_elements.append(ref)
        for s in stack:
            if s is root:
                continue
            s.page_range[0] = min(s.page_range[0], ref.page)
            s.page_range[1] = max(s.page_range[1], ref.page)

    return root, all_elements, max_page


def partition(
    pdf_file: Path,
    *,
    preflight: Any | None = None,
    on_stage: Callable[[str, float, dict[str, Any]], None] | None = None,
) -> tuple[Section, list[ElementRef], int, list[str]]:
    """Partition a PDF with Unstructured, routed by preflight classification.

    ``preflight`` is the result of :func:`app.processing.preflight.classify_pdf`.
    When it is omitted (tests, direct callers), the legacy behavior is kept:
    a ``fast`` pass, falling back to ``hi_res`` only when extraction yields
    essentially no text.  When provided, its ``route`` chooses the primary
    strategy and its ``num_pages`` drives the post-extraction quality gate.
    """
    from unstructured.partition.pdf import partition_pdf

    from app.processing.preflight import missing_pages, quality_gate

    warnings: list[str] = []
    forced = _forced_strategy()
    if preflight is not None and preflight.route:
        primary: str = preflight.route
        expected_pages: int = preflight.num_pages
    else:
        primary = forced or "fast"
        expected_pages = 0

    def _partition_with(strategy: str) -> list[Any]:
        return partition_pdf(
            filename=str(pdf_file),
            strategy=strategy,
            infer_table_structure=True,
            extract_images_in_pdf=False,
        )

    def _report_ocr(page_count: int | None) -> None:
        """Notify the caller that OCR is about to run (thread-safe callback)."""
        if on_stage is None:
            return
        if page_count:
            on_stage(
                "PDF contains images — running OCR on "
                f"{page_count} page(s), this can take a few minutes",
                0.25,
                {"ocr_pages": page_count},
            )
        else:
            on_stage(
                "PDF contains images — running OCR, this can take a few minutes",
                0.25,
                {},
            )

    try:
        if primary == "hi_res":
            _report_ocr(expected_pages or None)
        elements = _partition_with(primary)
    except Exception as e:
        if primary == "fast":
            raise
        log.warning(
            "partition with strategy=%s failed (%s: %s); retrying with fast: %s",
            primary,
            type(e).__name__,
            e,
            pdf_file,
        )
        warnings.append(
            "Primary document analysis could not run; a simpler text-only pass was used instead. "
            "Tables, figures, and layout may be less accurate."
        )
        elements = _partition_with("fast")

    if not forced and primary == "fast":
        gate_warnings = quality_gate(elements, expected_pages, classified_route="fast")
        if gate_warnings:
            warnings.extend(gate_warnings)
            missing = missing_pages(elements, expected_pages)
            missing_fraction = (
                len(missing) / expected_pages if expected_pages > 0 else 0.0
            )
            try:
                if (
                    expected_pages > 0
                    and missing
                    and missing_fraction >= FULL_DOC_HIRES_FRACTION
                ):
                    _report_ocr(len(missing))
                    log.info(
                        "fast extraction quality gate failed for %s (%s); "
                        "retrying whole document with hi_res",
                        pdf_file,
                        "; ".join(gate_warnings),
                    )
                    hi_res_elements = _partition_with("hi_res")
                    hi_res_gate = quality_gate(
                        hi_res_elements, expected_pages, classified_route="hi_res"
                    )
                    if len(hi_res_gate) < len(gate_warnings):
                        elements = hi_res_elements
                        warnings = [w for w in hi_res_gate if "no usable text" not in w]
                        warnings.insert(
                            0,
                            "The initial text-only pass looked low-quality; "
                            "a layout-aware pass was used instead.",
                        )
                    elif hi_res_gate and not any("no usable" in w for w in hi_res_gate):
                        warnings.extend(
                            "Layout-aware retry also produced incomplete output: " + w
                            for w in hi_res_gate
                        )
                elif (
                    expected_pages > 0
                    and missing
                    and missing_fraction >= MIN_HIRES_RETRY_FRACTION
                ):
                    _report_ocr(len(missing))
                    log.info(
                        "fast extraction quality gate failed for %s (%s); "
                        "retrying OCR on %d of %d pages",
                        pdf_file,
                        "; ".join(gate_warnings),
                        len(missing),
                        expected_pages,
                    )
                    targeted = _partition_pages_hi_res(pdf_file, missing)
                    merged = _merge_page_elements(elements, targeted, missing)
                    merged_gate = quality_gate(
                        merged, expected_pages, classified_route="hi_res"
                    )
                    if len(merged_gate) < len(gate_warnings):
                        elements = merged
                        warnings = [w for w in merged_gate if "no usable text" not in w]
                        warnings.insert(
                            0,
                            "Some pages lacked extractable text; a layout-aware "
                            "pass was used on those pages.",
                        )
                    elif merged_gate and not any("no usable" in w for w in merged_gate):
                        warnings.extend(
                            "Layout-aware retry also produced incomplete output: " + w
                            for w in merged_gate
                        )
                    else:
                        warnings.append(
                            f"OCR on {len(missing)} page(s) did not recover usable text."
                        )
            except Exception as e:
                log.warning(
                    "hi_res partition failed (%s: %s); continuing with fast output only: %s",
                    type(e).__name__,
                    e,
                    pdf_file,
                )
                warnings.append(
                    "Layout-aware processing could not run for this file "
                    "(format or rendering issue). The manuscript was indexed "
                    "from basic text only. Structure, tables, and figures "
                    "may be incomplete."
                )

    root, all_elements, num_pages = build_tree(elements)
    return root, all_elements, num_pages, warnings


def _forced_strategy() -> str | None:
    import os

    value = os.getenv("UNSTRUCTURED_STRATEGY", "").strip().lower()
    return value or None


def _page_number(element: Any) -> int:
    meta = getattr(element, "metadata", None)
    return int(getattr(meta, "page_number", None) or 1)


def _partition_pages_hi_res(pdf_file: Path, page_numbers: list[int]) -> list[Any]:
    """Run hi_res OCR only on the given 1-indexed pages.

    The requested pages are extracted into a temporary PDF and partitioned
    once (so layout/OCR models load a single time), then element page numbers
    are remapped back to the original document.
    """
    from unstructured.partition.pdf import partition_pdf

    import fitz

    with tempfile.TemporaryDirectory() as td:
        subset_path = Path(td) / "ocr-subset.pdf"
        with fitz.open(str(pdf_file)) as src:
            subset = fitz.open()
            try:
                for page in page_numbers:
                    subset.insert_pdf(src, from_page=page - 1, to_page=page - 1)
                subset.save(str(subset_path))
            finally:
                subset.close()
        elements = partition_pdf(
            filename=str(subset_path),
            strategy="hi_res",
            infer_table_structure=True,
            extract_images_in_pdf=False,
        )
        for el in elements:
            meta = getattr(el, "metadata", None)
            if meta is not None and hasattr(meta, "page_number"):
                subset_page = int(getattr(meta, "page_number", 1) or 1)
                if 1 <= subset_page <= len(page_numbers):
                    meta.page_number = page_numbers[subset_page - 1]
        return elements


def _merge_page_elements(
    elements: list[Any], targeted: list[Any], missing_pages: list[int]
) -> list[Any]:
    """Replace fast-pass elements on the missing pages with OCR'd ones."""
    missing = set(missing_pages)
    kept = [el for el in elements if _page_number(el) not in missing]
    return kept + list(targeted)
