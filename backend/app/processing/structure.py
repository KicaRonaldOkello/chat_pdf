from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ElementRef:
    id: str
    type: str  # "text" | "table" | "image" | "formula"
    page: int
    text: str = ""
    bbox: list[float] | None = None  # [x0, y0, x1, y1] when available
    page_size: list[float] | None = None  # [width, height] of that coord system
    extra: dict[str, Any] = field(default_factory=dict)


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


def partition(pdf_file: Path) -> tuple[Section, list[ElementRef], int, list[str]]:
    import os

    from unstructured.partition.pdf import partition_pdf

    warnings: list[str] = []
    forced = os.getenv("UNSTRUCTURED_STRATEGY", "").strip().lower()
    primary = forced or "fast"

    try:
        elements = partition_pdf(
            filename=str(pdf_file),
            strategy=primary,
            infer_table_structure=True,
            extract_images_in_pdf=False,
        )
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
        elements = partition_pdf(
            filename=str(pdf_file),
            strategy="fast",
            infer_table_structure=True,
            extract_images_in_pdf=False,
        )

    if not forced and primary == "fast":
        total_chars = sum(len(getattr(el, "text", "") or "") for el in elements)
        if total_chars < 50:
            try:
                elements = partition_pdf(
                    filename=str(pdf_file),
                    strategy="hi_res",
                    infer_table_structure=True,
                    extract_images_in_pdf=False,
                )
            except Exception as e:
                # hi_res uses pypdfium2 + layout model; some PDFs fail with Pdfium
                # "Data format error" or similar while fast/pdfminer text still works;
                # others are simply too short (scanned/cover) — keep the fast result.
                log.warning(
                    "hi_res partition failed (%s: %s); continuing with fast output only: %s",
                    type(e).__name__,
                    e,
                    pdf_file,
                )
                warnings.append(
                    "Layout-aware processing could not run for this file (format or rendering issue). "
                    "The manuscript was indexed from basic text only. "
                    "Structure, tables, and figures may be incomplete."
                )

    root, all_elements, num_pages = build_tree(elements)
    return root, all_elements, num_pages, warnings
