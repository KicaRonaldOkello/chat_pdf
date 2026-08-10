"""Input validation and resource-limit tests (synthetic PDFs)."""

from __future__ import annotations

from pathlib import Path

import fitz

from app.processing.validation import (
    inspect_resource_limits,
    validate_pdf_bytes,
)


def _text_pdf(tmp_path: Path, pages: int = 3, name: str = "doc.pdf") -> Path:
    path = tmp_path / name
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), "Alpha beta gamma delta. " * 20)
    doc.save(path)
    doc.close()
    return path


def _image_pdf(tmp_path: Path) -> Path:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 200), False)
    pix.clear_with(150)
    img = tmp_path / "img.png"
    pix.save(img)
    path = tmp_path / "images.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(fitz.Rect(50, 50, 300, 300), filename=str(img))
    doc.save(path)
    doc.close()
    return path


def test_rejects_non_pdf_magic_bytes() -> None:
    result = validate_pdf_bytes(b"PK\x03\x04 not a pdf at all")
    assert result.is_pdf is False
    assert result.readable is False


def test_accepts_real_pdf(tmp_path: Path) -> None:
    result = validate_pdf_bytes(_text_pdf(tmp_path))
    assert result.is_pdf is True
    assert result.readable is True
    assert result.num_pages == 3


def test_magic_bytes_alone_insufficient(tmp_path: Path) -> None:
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"%PDF-1.4 this is not a parseable pdf")
    result = validate_pdf_bytes(path)
    assert result.is_pdf is True
    assert result.readable is False


def test_resource_limits_counts_images_and_streams(tmp_path: Path) -> None:
    result = inspect_resource_limits(_image_pdf(tmp_path))
    assert result.readable is True
    assert result.image_count == 1
    assert result.decompressed_bytes > 0
    assert result.limits_exceeded == []


def test_resource_limits_flags_too_many_pages(tmp_path: Path, monkeypatch) -> None:
    from app.processing.validation import settings

    monkeypatch.setattr(settings, "max_pdf_pages", 2)
    result = inspect_resource_limits(_text_pdf(tmp_path, pages=4))
    assert any("pages=" in limit for limit in result.limits_exceeded)
