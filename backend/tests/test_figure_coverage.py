"""Phase 7: figure coverage — vector-chart detection and visual nomination."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest

from app.processing.images import detect_vector_visual_pages, enrich_images
from app.processing.structure import ElementRef, Section


def _vector_chart_pdf(tmp_path: Path, name: str = "charts.pdf") -> Path:
    path = tmp_path / name
    doc = fitz.open()
    page = doc.new_page()
    for x0, y0 in ((50, 50), (250, 50), (50, 300), (250, 300)):
        page.draw_rect(
            fitz.Rect(x0, y0, x0 + 200, y0 + 200), color=(0, 0, 1), fill=(0, 0, 1)
        )
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Plain prose only. " * 50, fontsize=11)
    doc.save(path)
    doc.close()
    return path


def _root() -> Section:
    return Section(
        id="root",
        title="(root)",
        level=0,
        path="",
        page_range=[1, 2],
        children=[
            Section(
                id="sec-1",
                title="Report",
                level=1,
                path="Report",
                page_range=[1, 2],
            )
        ],
    )


def test_detect_vector_visual_pages_finds_chart_page(tmp_path: Path) -> None:
    path = _vector_chart_pdf(tmp_path)
    pages = detect_vector_visual_pages(path)
    assert pages == [1]


def test_detect_vector_visual_pages_ignores_prose(tmp_path: Path) -> None:
    path = tmp_path / "prose.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "hello world " * 100, fontsize=11)
    doc.save(path)
    doc.close()
    assert detect_vector_visual_pages(path) == []


@pytest.mark.asyncio
async def test_enrich_images_creates_vector_placeholder_with_nearby_text(
    tmp_path: Path,
) -> None:
    path = _vector_chart_pdf(tmp_path)
    root = _root()
    text_el = ElementRef(
        id="el-t1", type="text", page=1, text="Revenue growth chart by quarter"
    )
    root.children[0].elements.append(text_el)
    placeholders: list[ElementRef] = [text_el]

    with patch(
        "app.processing.images.get_storage",
        return_value=MagicMock(put_image_bytes=MagicMock(return_value="img-key")),
    ):
        await enrich_images(path, "doc-v", placeholders, root, el_id_start=100)

    vector_els = [
        el
        for section in [root, *root.children]
        for el in section.elements
        if el.type == "image" and el.extra.get("vector_visual")
    ]
    assert len(vector_els) == 1
    el = vector_els[0]
    assert el.page == 1
    assert el.extra["vision_analyzed"] is False
    assert "Revenue growth" in el.extra.get("nearby_text", "")


@pytest.mark.asyncio
async def test_enrich_images_does_not_duplicate_raster_pages(tmp_path: Path) -> None:
    """A page with an existing raster image placeholder is not duplicated."""
    path = _vector_chart_pdf(tmp_path)
    root = _root()
    existing = ElementRef(
        id="el-img",
        type="image",
        page=1,
        text="",
        extra={"path": "raster.png"},
    )
    root.children[0].elements.append(existing)
    placeholders = [existing]

    with patch("app.processing.images.get_storage") as storage:
        storage.return_value.put_image_bytes.return_value = "k"
        await enrich_images(path, "doc-v2", placeholders, root, el_id_start=100)

    image_els = [
        el
        for section in [root, *root.children]
        for el in section.elements
        if el.type == "image"
    ]
    assert len(image_els) == 1
    assert image_els[0].id == "el-img"
