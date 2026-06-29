from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import tiktoken

from app.config import CHUNK_OVERLAP, CHUNK_TOKENS
from app.processing.structure import ElementRef, Section
from app.processing.tables import count_table_rows
from app.processing.tree import walk_sections
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


def mk_id(doc_id: str, *parts: str) -> str:
    return f"{doc_id}::" + "::".join(parts)


def chunk_section_text(
    section: Section, doc_id: str, next_idx: int
) -> tuple[list[Chunk], int]:
    text_els = [e for e in section.elements if e.type in ("text", "formula")]
    if not text_els:
        return [], next_idx

    blob_parts: list[str] = []
    element_ids: list[str] = []
    first_page = section.page_range[0]
    for e in text_els:
        if not e.text:
            continue
        blob_parts.append(e.text)
        element_ids.append(e.id)
    if not blob_parts:
        return [], next_idx
    blob = "\n\n".join(blob_parts)

    bbox, page_size = union_bbox(text_els, first_page)

    windows = token_split(blob, CHUNK_TOKENS, CHUNK_OVERLAP)
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
    table_index = next_idx  # stable index used in the file path

    pr = el.extra.get("page_range", [el.page, el.page])
    if isinstance(pr, list) and len(pr) == 2 and pr[0] != pr[1]:
        header = f"[Table on pp.{pr[0]}-{pr[1]}]"
    else:
        header = f"[Table on p.{el.page}]"
    if caption_source:
        header += f" {caption_source}"

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
    if not caption and not description:
        return None, next_idx

    header = f"[Figure on p.{el.page}]"
    if caption:
        header += f" {caption}"
    embed = header + ("\n" + description if description else "")
    display = embed

    cid = mk_id(doc_id, "image", str(next_idx))
    return (
        Chunk(
            chunk_id=cid,
            document_id=doc_id,
            element_ids=[el.id],
            type="image",
            section_path=section.path,
            page=el.page,
            text_for_embedding=embed,
            display_text=display,
            bbox=list(el.bbox) if el.bbox else None,
            page_size=list(el.page_size) if el.page_size else None,
            extra={
                "caption": caption,
                "image_path": el.extra.get("path", ""),
            },
        ),
        next_idx + 1,
    )


def build_chunks(root: Section, document_id: str) -> list[Chunk]:
    sections: list[Section] = list(walk_sections(root))
    if not sections or any(e.type != "text" for e in root.elements):
        sections.insert(0, root)

    out: list[Chunk] = []
    idx = 0
    for sec in sections:
        text_chunks, idx = chunk_section_text(sec, document_id, idx)
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
