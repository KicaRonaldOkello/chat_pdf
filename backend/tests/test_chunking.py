"""Unit tests for PDF/chunk construction (pure logic)."""

from __future__ import annotations

from app.processing.chunking import (
    Chunk,
    build_chunks,
    chunk_image,
    chunk_section_text,
    chunk_table,
    mk_id,
    token_split,
    union_bbox,
)
from app.processing.structure import ElementRef, Section


def test_mk_id_stable_parts() -> None:
    assert mk_id("doc1", "text", "0") == "doc1::text::0"


def test_token_split_empty() -> None:
    assert token_split("", 100, 10) == []
    assert token_split("   \n\t  ", 100, 10) == []


def test_token_split_short_returns_single_window() -> None:
    assert token_split("hello", 100, 10) == ["hello"]


def test_token_split_windows_respect_overlap() -> None:
    # Force multiple windows with small target and overlap
    long = "word " * 200
    parts = token_split(long, target=20, overlap=5)
    assert len(parts) >= 2
    assert all(p.strip() for p in parts)


def test_union_bbox_same_page_merges() -> None:
    els = [
        ElementRef(
            id="a",
            type="text",
            page=1,
            bbox=[0.0, 0.0, 10.0, 10.0],
            page_size=[100.0, 100.0],
        ),
        ElementRef(
            id="b",
            type="text",
            page=1,
            bbox=[5.0, 5.0, 20.0, 20.0],
            page_size=[100.0, 100.0],
        ),
    ]
    bbox, page_size = union_bbox(els, page=1)
    assert page_size == [100.0, 100.0]
    assert bbox == [0.0, 0.0, 20.0, 20.0]


def test_union_bbox_skips_other_page() -> None:
    els = [
        ElementRef(
            id="a",
            type="text",
            page=1,
            bbox=[0.0, 0.0, 1.0, 1.0],
            page_size=[10.0, 10.0],
        ),
        ElementRef(
            id="b",
            type="text",
            page=2,
            bbox=[9.0, 9.0, 10.0, 10.0],
            page_size=[10.0, 10.0],
        ),
    ]
    bbox, page_size = union_bbox(els, page=1)
    assert bbox == [0.0, 0.0, 1.0, 1.0]
    assert page_size == [10.0, 10.0]


def test_chunk_section_text_embeds_section_path() -> None:
    sec = Section(
        id="s1",
        title="Intro",
        level=1,
        path="Document > Intro",
        page_range=[1, 1],
        elements=[
            ElementRef(id="e1", type="text", page=1, text="Alpha"),
            ElementRef(id="e2", type="text", page=1, text="Beta"),
        ],
    )
    chunks, nxt = chunk_section_text(sec, "doc-9", 0)
    assert nxt == 1
    assert len(chunks) == 1
    c = chunks[0]
    assert c.document_id == "doc-9"
    assert c.type == "text"
    assert c.section_path == "Document > Intro"
    assert "Alpha" in c.display_text and "Beta" in c.display_text
    assert c.text_for_embedding.startswith("Document > Intro\n\n")


def test_chunk_table_prefers_markdown_else_html() -> None:
    sec = Section(
        id="s1",
        title="T",
        level=1,
        path="Doc",
        page_range=[2, 2],
        elements=[],
    )
    el = ElementRef(
        id="t1",
        type="table",
        page=2,
        text="My caption",
        extra={"html": "<table></table>", "description": "d"},
    )
    ch, nxt = chunk_table(sec, el, "d1", 0)
    assert ch is not None
    assert ch.type == "table"
    assert "[Table on p.2]" in ch.text_for_embedding
    assert "My caption" in ch.text_for_embedding
    assert nxt == 1


def test_chunk_table_returns_none_without_content() -> None:
    sec = Section(
        id="s1",
        title="T",
        level=1,
        path="Doc",
        page_range=[1, 1],
        elements=[],
    )
    el = ElementRef(id="t1", type="table", page=1, text="", extra={})
    ch, nxt = chunk_table(sec, el, "d1", 0)
    assert ch is None
    assert nxt == 0


def test_chunk_image_uses_caption_and_description() -> None:
    sec = Section(
        id="s1",
        title="Fig",
        level=1,
        path="Doc",
        page_range=[3, 3],
        elements=[],
    )
    el = ElementRef(
        id="i1",
        type="image",
        page=3,
        text="alt",
        extra={"caption": "cap", "description": "long desc"},
    )
    ch, nxt = chunk_image(sec, el, "d1", 0)
    assert ch is not None
    assert ch.type == "image"
    assert "[Figure on p.3]" in ch.text_for_embedding
    assert "long desc" in ch.text_for_embedding
    assert ch.extra.get("caption") == "cap"
    assert nxt == 1


def test_build_chunks_orders_text_then_table() -> None:
    root = Section(
        id="root",
        title="R",
        level=0,
        path="Document",
        page_range=[1, 1],
        elements=[
            ElementRef(id="x1", type="text", page=1, text="Body"),
            ElementRef(
                id="tb",
                type="table",
                page=1,
                text="",
                extra={"markdown": "|a|", "description": ""},
            ),
        ],
        children=[],
    )
    chunks = build_chunks(root, "doc-x")
    types = [c.type for c in chunks]
    assert types[0] == "text"
    assert "table" in types


def test_chunk_payload_includes_optional_bbox() -> None:
    c = Chunk(
        chunk_id="id",
        document_id="d",
        element_ids=["e"],
        type="text",
        section_path="P",
        page=1,
        text_for_embedding="t",
        display_text="d",
        bbox=[0, 0, 1, 1],
        page_size=[10, 10],
    )
    p = c.payload()
    assert p["bbox"] == [0, 0, 1, 1]
    assert p["page_size"] == [10, 10]
