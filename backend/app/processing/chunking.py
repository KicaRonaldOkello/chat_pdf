from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import tiktoken

from app.processing.structure import ElementRef, Section
from app.processing.tables import count_table_rows
from app.processing.tree import walk_sections
from app.settings import settings
from app.storage import get_storage

TABLE_ROW_THRESHOLD = 100
TABLE_PREVIEW_ROWS = 30

ENC = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    element_ids: list[str]
    type: str  # "text" | "table" | "image"
    section_path: str
    page: int
    text_for_embedding: str
    display_text: str
    bbox: list[float] | None = None  # [x0, y0, x1, y1] in page_size coord system
    page_size: list[float] | None = None  # [width, height]
    extra: dict[str, Any] = field(default_factory=dict)

    def payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
            "element_ids": self.element_ids,
            "type": self.type,
            "section_path": self.section_path,
            "page": self.page,
            "display_text": self.display_text,
            **self.extra,
        }
        if self.bbox:
            out["bbox"] = self.bbox
        if self.page_size:
            out["page_size"] = self.page_size
        return out


def union_bbox(
    elements: list[ElementRef], page: int
) -> tuple[list[float] | None, list[float] | None]:
    bbox: list[float] | None = None
    page_size: list[float] | None = None
    for e in elements:
        if e.page != page or not e.bbox or not e.page_size:
            continue
        if page_size is None:
            page_size = list(e.page_size)
        elif page_size != list(e.page_size):
            continue
        if bbox is None:
            bbox = list(e.bbox)
        else:
            bbox = [
                min(bbox[0], e.bbox[0]),
                min(bbox[1], e.bbox[1]),
                max(bbox[2], e.bbox[2]),
                max(bbox[3], e.bbox[3]),
            ]
    return bbox, page_size


def token_split(text: str, target: int, overlap: int) -> list[str]:
    if not text.strip():
        return []
    tokens = ENC.encode(text)
    if len(tokens) <= target:
        return [text]
    step = max(1, target - overlap)
    out: list[str] = []
    for start in range(0, len(tokens), step):
        window = tokens[start : start + target]
        if not window:
            break
        out.append(ENC.decode(window))
        if start + target >= len(tokens):
            break
    return out


def _heuristic_table_descriptor(markdown: str, *, max_items: int = 25) -> str:
    """Build a keyword-rich descriptor from row labels in *markdown*.

    Used as a fallback when the LLM-generated table description is empty.
    Extracts the first two columns (typically an indicator code + label)
    and emits a dense line that anchors the embedding for topical queries.
    """
    lines = markdown.strip().splitlines()
    labels: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 2:
            continue
        # Skip separator rows, sub-headers, and noise
        if all(c.replace("-", "").replace(":", "").strip() == "" for c in cells if c):
            continue
        # Prefer col-1 (description); fall back to col-0 (code)
        label = cells[1] or cells[0]
        if not label or len(label) < 5:
            continue
        # Skip generic labels that are clearly not indicator names
        low = label.lower()
        if low in ("description", "indicator", "indicator code", "code"):
            continue
        # Normalise and deduplicate
        key = low
        if key in seen:
            continue
        seen.add(key)
        # Truncate long labels conservatively
        labels.append(label[:200])
        if len(labels) >= max_items:
            break
    if not labels:
        return ""
    return "Key indicators: " + "; ".join(labels)


def mk_id(doc_id: str, *parts: str) -> str:
    return f"{doc_id}::" + "::".join(parts)


def chunk_section_text(
    section: Section,
    doc_id: str,
    next_idx: int,
    *,
    watermark_texts: set[str] | None = None,
) -> tuple[list[Chunk], int]:
    text_els = [e for e in section.elements if e.type in ("text", "formula")]
    if not text_els:
        return [], next_idx

    blob_parts: list[str] = []
    element_ids: list[str] = []
    first_page = section.page_range[0]
    _skip = watermark_texts or set()
    for e in text_els:
        if not e.text or e.text in _skip:
            continue
        blob_parts.append(e.text)
        element_ids.append(e.id)
    if not blob_parts:
        return [], next_idx
    blob = "\n\n".join(blob_parts)

    bbox, page_size = union_bbox(text_els, first_page)

    windows = token_split(blob, settings.chunk_tokens, settings.chunk_overlap)
    chunks: list[Chunk] = []
    for w in windows:
        cid = mk_id(doc_id, "text", str(next_idx))
        next_idx += 1
        embed = f"{section.path}\n\n{w}"
        chunks.append(
            Chunk(
                chunk_id=cid,
                document_id=doc_id,
                element_ids=element_ids,
                type="text",
                section_path=section.path,
                page=first_page,
                text_for_embedding=embed,
                display_text=w,
                bbox=bbox,
                page_size=page_size,
            )
        )
    return chunks, next_idx


def chunk_table(
    section: Section, el: ElementRef, doc_id: str, next_idx: int
) -> tuple[Chunk | None, int]:
    markdown = str(el.extra.get("markdown") or "")
    description = str(el.extra.get("description") or "")
    html = str(el.extra.get("html") or "")
    caption_source = el.text or ""

    if not markdown and html:
        markdown = html
    if not markdown and not description:
        return None, next_idx

    data_rows, ncols = count_table_rows(markdown)

    # ── Per-element table validation ────────────────────────────────
    # Skip phantom tables that camelot finds in scanned/image pages.
    # These have garbled single-column content with no real data.
    if ncols <= 1 and markdown and data_rows <= 1:
        import re as _re

        _cells = [
            c.strip()
            for line in markdown.splitlines()
            if line.startswith("|")
            for c in line.split("|")[1:-1]
        ]
        _nonempty = [c for c in _cells if c and c != "---"]
        if _nonempty:
            _garbled = sum(
                1
                for c in _nonempty
                if " " not in c and len(c) > 15 and _re.search(r"[^\w\s]", c)
            )
            if _garbled / len(_nonempty) > 0.5:
                return None, next_idx

    table_index = next_idx  # stable index used in the file path

    pr = el.extra.get("page_range", [el.page, el.page])
    if isinstance(pr, list) and len(pr) == 2 and pr[0] != pr[1]:
        header = f"[Table on pp.{pr[0]}-{pr[1]}]"
    else:
        header = f"[Table on p.{el.page}]"
    if caption_source:
        header += f" {caption_source}"

    # When the LLM-generated description is empty or missing, build a
    # heuristic one from row labels so the embedding has focused keywords
    # near the top instead of being diluted by the full markdown.
    if not description and markdown:
        description = _heuristic_table_descriptor(markdown, max_items=25)

    # ── Small / medium table: full markdown in Qdrant ─────────────────
    if data_rows <= TABLE_ROW_THRESHOLD:
        embed_parts = [header]
        if description:
            embed_parts.append(description)
        if markdown:
            embed_parts.append(markdown[:3000])
        embed = "\n".join(embed_parts)

        display_parts = [header]
        if description:
            display_parts.append(description)
        if markdown:
            display_parts.append(markdown)
        display = "\n\n".join(display_parts)

        extra: dict[str, Any] = {
            "caption": caption_source,
            "table_rows": data_rows,
            "table_cols": ncols,
        }

    # ── Large table: descriptor + preview in Qdrant, full md on disk ───
    else:
        lines = markdown.strip().splitlines()
        preview_end = min(len(lines), 2 + TABLE_PREVIEW_ROWS)
        preview_md = "\n".join(lines[:preview_end])
        remaining = data_rows - TABLE_PREVIEW_ROWS

        embed_parts = [header]
        if description:
            embed_parts.append(description)
        embed_parts.append(preview_md[:3000])
        embed = "\n".join(embed_parts)

        display_parts = [header]
        if description:
            display_parts.append(description)
        display_parts.append(preview_md)
        display_parts.append(
            f"\n[Full table has {remaining} more rows — stored on disk]"
        )
        display = "\n\n".join(display_parts)

        table_path = get_storage().put_table_markdown(
            doc_id, table_index, markdown
        )
        extra = {
            "caption": caption_source,
            "table_rows": data_rows,
            "table_cols": ncols,
            "table_path": table_path,
            "table_truncated": True,
        }

    cid = mk_id(doc_id, "table", str(next_idx))
    return (
        Chunk(
            chunk_id=cid,
            document_id=doc_id,
            element_ids=[el.id],
            type="table",
            section_path=section.path,
            page=el.page,
            text_for_embedding=embed,
            display_text=display,
            bbox=list(el.bbox) if el.bbox else None,
            page_size=list(el.page_size) if el.page_size else None,
            extra=extra,
        ),
        next_idx + 1,
    )


def chunk_image(
    section: Section, el: ElementRef, doc_id: str, next_idx: int
) -> tuple[Chunk | None, int]:
    caption = str(el.extra.get("caption") or el.text or "")
    description = str(el.extra.get("description") or "")
    image_path = str(el.extra.get("path") or "")
    vision_analyzed = bool(el.extra.get("vision_analyzed", False))

    # Skip only if there is literally nothing to embed — no image file,
    # no caption, and no section context.
    if not image_path and not caption and not section.path:
        return None, next_idx

    header = f"[Figure on p.{el.page}]"
    if caption:
        header += f" {caption}"

    # Embedding signal — always includes section context so the image is
    # retrievable even before vision analysis runs.  For unanalysed images
    # we also pull a short snippet of nearby text so that topical keywords
    # (e.g. "inflation", "exchange rate") anchor the vector.
    embed_parts = [header]
    if description:
        embed_parts.append(description)
    else:
        embed_parts.append(f"Section: {section.path}")
        # Nearby text from the same page — pre-computed during ingestion
        # so image chunks have topical keywords for retrieval.
        nearby = str(el.extra.get("nearby_text") or "")
        if nearby:
            embed_parts.append(f"Nearby text: {nearby[:500]}")
        embed_parts.append("Visual analysis available on demand.")

    display_parts = [header]
    if description:
        display_parts.append(description)
    elif not vision_analyzed:
        display_parts.append("(Visual analysis available on demand)")

    cid = mk_id(doc_id, "image", str(next_idx))
    return (
        Chunk(
            chunk_id=cid,
            document_id=doc_id,
            element_ids=[el.id],
            type="image",
            section_path=section.path,
            page=el.page,
            text_for_embedding="\n".join(embed_parts),
            display_text="\n".join(display_parts),
            bbox=list(el.bbox) if el.bbox else None,
            page_size=list(el.page_size) if el.page_size else None,
            extra={
                "caption": caption,
                "image_path": image_path,
                "vision_analyzed": vision_analyzed,
            },
        ),
        next_idx + 1,
    )


def _find_watermark_texts(sections: list[Section]) -> set[str]:
    """Return the set of text blobs that appear identically on 3+ pages.

    Scanned PDFs often have a header/footer watermark on every page
    (e.g. \"Downloaded by John Lyomoki...\").  Embedding these 50+ times
    wastes time and pollutes retrieval.
    """

    blob_pages: dict[str, set[int]] = {}
    for sec in sections:
        for el in sec.elements:
            if el.type == "text" and el.text and len(el.text) > 30:
                first_page = el.page
                blob_pages.setdefault(el.text, set()).add(first_page)
    return {blob for blob, pages in blob_pages.items() if len(pages) >= 3}


def build_chunks(root: Section, document_id: str) -> list[Chunk]:
    sections: list[Section] = list(walk_sections(root))
    if not sections or any(e.type != "text" for e in root.elements):
        sections.insert(0, root)

    watermark_texts = _find_watermark_texts(sections)

    out: list[Chunk] = []
    idx = 0
    for sec in sections:
        text_chunks, idx = chunk_section_text(
            sec, document_id, idx, watermark_texts=watermark_texts
        )
        out.extend(text_chunks)
        for el in sec.elements:
            if el.type == "table":
                c, idx = chunk_table(sec, el, document_id, idx)
                if c:
                    out.append(c)
            elif el.type == "image":
                c, idx = chunk_image(sec, el, document_id, idx)
                if c:
                    out.append(c)
    return out
