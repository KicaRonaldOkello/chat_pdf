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
) -> tuple[Section, list[ElementRef], int, list[str]]:
    """Partition a PDF with Unstructured, routed by preflight classification.

    ``preflight`` is the result of :func:`app.processing.preflight.classify_pdf`.
    When it is omitted (tests, direct callers), the legacy behavior is kept:
    a ``fast`` pass, falling back to ``hi_res`` only when extraction yields
    essentially no text.  When provided, its ``route`` chooses the primary
    strategy and its ``num_pages`` drives the post-extraction quality gate.
    """
    from unstructured.partition.pdf import partition_pdf

    from app.processing.preflight import quality_gate

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

    try:
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
            try:
                log.info(
                    "fast extraction quality gate failed for %s (%s); "
                    "retrying with hi_res",
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
