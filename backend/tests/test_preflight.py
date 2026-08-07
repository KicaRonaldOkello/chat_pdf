"""Preflight classification and quality-gate tests (synthetic PDFs only)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fitz
import pytest

from app.processing.preflight import (
    DocumentPreflight,
    PreflightError,
    classify_pdf,
    quality_gate,
)
from app.processing.structure import partition


def _write_pdf(
    tmp_path: Path,
    *,
    pages: list[dict[str, object]],
    name: str = "sample.pdf",
    encrypt: bool = False,
) -> Path:
    path = tmp_path / name
    doc = fitz.open()
    for spec in pages:
        page = doc.new_page()
        text = spec.get("text", "")
        if text:
            page.insert_text((72, 72), str(text), fontsize=11)
        image = spec.get("image")
        if image:
            rect = fitz.Rect(*(float(x) for x in image["rect"]))
            page.insert_image(rect, filename=str(image["path"]))
    if encrypt:
        doc.save(
            path,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            owner_pw="owner",
            user_pw="user",
        )
    else:
        doc.save(path)
    doc.close()
    return path


def _solid_image(tmp_path: Path, name: str = "scan.png") -> Path:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 400), False)
    pix.clear_with(180)
    img_path = tmp_path / name
    pix.save(img_path)
    return img_path


def _element(
    category: str,
    text: str,
    page: int,
    *,
    image_path: str | None = None,
) -> SimpleNamespace:
    meta = SimpleNamespace(page_number=page)
    if image_path:
        meta.image_path = image_path
    return SimpleNamespace(category=category, text=text, metadata=meta)


def test_text_pdf_routes_fast(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path,
        pages=[
            {"text": "Alpha beta gamma delta. " * 20},
            {"text": "Epsilon zeta eta theta. " * 20},
        ],
    )

    result = classify_pdf(path)

    assert result.classification == "text"
    assert result.confidence == "medium"  # pdf-inspector: sparse synthetic text
    assert result.route == "fast"
    assert result.num_pages == 2
    assert result.ocr_pages == []


def test_image_only_scan_routes_hi_res(tmp_path: Path) -> None:
    scan = _solid_image(tmp_path)
    path = _write_pdf(
        tmp_path,
        pages=[
            {"image": {"rect": [30, 30, 560, 750], "path": scan}},
            {"image": {"rect": [30, 30, 560, 750], "path": scan}},
        ],
    )

    result = classify_pdf(path)

    assert result.classification == "scanned"
    assert result.route == "hi_res"
    assert result.ocr_pages == [0, 1]


def test_image_heavy_pdf_routes_hi_res_and_lists_ocr_pages(tmp_path: Path) -> None:
    """Real pdf-inspector integration: a mixed page image + text pages must
    still go to the OCR-capable route (pdf-inspector may label it scanned or
    image_based depending on text-operator density)."""
    scan = _solid_image(tmp_path)
    path = _write_pdf(
        tmp_path,
        pages=[
            {
                "text": "Chapter one. " * 25,
                "image": {"rect": [100, 100, 500, 500], "path": scan},
            },
            {"text": "Chapter two. " * 25},
        ],
    )

    result = classify_pdf(path)

    assert result.classification in ("scanned", "mixed")
    assert result.route == "hi_res"
    assert result.ocr_pages == [0, 1]


def test_sparse_cover_page_does_not_classify_whole_doc_scanned(
    tmp_path: Path,
) -> None:
    path = _write_pdf(
        tmp_path,
        pages=[
            {"text": "Annual Report"},
            {"text": "Body paragraph number one. " * 20},
            {"text": "Body paragraph number two. " * 20},
        ],
    )

    result = classify_pdf(path)

    assert result.classification == "text"
    assert result.route == "fast"
    assert result.confidence == "medium"


def test_corrupt_pdf_raises_terminal_error(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"%PDF-1.4 garbage that is not a real pdf at all")

    with pytest.raises(PreflightError) as excinfo:
        classify_pdf(path)

    assert excinfo.value.status == "invalid"


def test_encrypted_pdf_raises_terminal_error(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path,
        pages=[{"text": "Secret content " * 20}],
        encrypt=True,
    )

    with pytest.raises(PreflightError) as excinfo:
        classify_pdf(path)

    assert excinfo.value.status == "encrypted"


def test_pdf_inspector_text_result_routes_fast(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, pages=[{"text": "Some text. " * 20}])
    fake = SimpleNamespace(
        pdf_type="text_based",
        confidence=0.9,
        page_count=1,
        pages_needing_ocr=[],
    )

    with patch("pdf_inspector.classify_pdf", return_value=fake):
        result = classify_pdf(path)

    assert result.classification == "text"
    assert result.route == "fast"
    assert result.confidence == "high"
    assert result.classifier == "pdf-inspector"
    assert result.ocr_pages == []


def test_pdf_inspector_scanned_result_routes_hi_res_and_records_ocr_pages(
    tmp_path: Path,
) -> None:
    path = _write_pdf(tmp_path, pages=[{"text": "Some text. " * 20}])
    fake = SimpleNamespace(
        pdf_type="scanned",
        confidence=0.95,
        page_count=2,
        pages_needing_ocr=[0, 1],
    )

    with patch("pdf_inspector.classify_pdf", return_value=fake):
        result = classify_pdf(path)

    assert result.classification == "scanned"
    assert result.route == "hi_res"
    assert result.confidence == "high"
    assert result.ocr_pages == [0, 1]


def test_pdf_inspector_image_based_and_mixed_map_to_hi_res(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, pages=[{"text": "Some text. " * 20}])

    for pdf_type in ("image_based", "mixed"):
        fake = SimpleNamespace(
            pdf_type=pdf_type,
            confidence=0.7,
            page_count=1,
            pages_needing_ocr=[0],
        )
        with patch("pdf_inspector.classify_pdf", return_value=fake):
            result = classify_pdf(path)
        assert result.route == "hi_res", pdf_type


def test_pdf_inspector_sparse_text_still_routes_fast(tmp_path: Path) -> None:
    """A legitimate sparse text PDF must not be pushed to hi_res."""
    path = _write_pdf(tmp_path, pages=[{"text": "Cover page"}])
    fake = SimpleNamespace(
        pdf_type="text_based",
        confidence=0.5,
        page_count=1,
        pages_needing_ocr=[],
    )

    with patch("pdf_inspector.classify_pdf", return_value=fake):
        result = classify_pdf(path)

    assert result.route == "fast"
    assert result.confidence == "medium"


def test_preflight_dict_round_trip() -> None:
    result = DocumentPreflight(
        classification="text",
        route="fast",
        confidence="high",
        num_pages=1,
        ocr_pages=[],
    )
    data = result.to_dict()
    assert data["classification"] == "text"
    assert data["route"] == "fast"


def test_quality_gate_warns_when_pages_missing() -> None:
    elements = [
        _element("NarrativeText", "Good page one text. " * 10, 1),
    ]

    warnings = quality_gate(elements, expected_pages=3, classified_route="fast")

    assert any("2 of 3 pages" in w for w in warnings)


def test_quality_gate_warns_garbled_text() -> None:
    elements = [
        _element("NarrativeText", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", 1),
        _element("NarrativeText", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", 1),
        _element("NarrativeText", "cccccccccccccccccccccccccccccccccccccccccc", 1),
    ]

    warnings = quality_gate(elements, expected_pages=1, classified_route="fast")

    assert any("garbled" in w for w in warnings)


def test_quality_gate_warns_no_output_at_all() -> None:
    elements: list[SimpleNamespace] = []

    warnings = quality_gate(elements, expected_pages=2, classified_route="fast")

    assert any("no usable text or images" in w for w in warnings)


def test_partition_uses_preflight_route_and_retries_fast_low_quality(
    tmp_path: Path,
) -> None:
    preflight = DocumentPreflight(
        classification="text",
        route="fast",
        confidence="high",
        num_pages=2,
    )
    good_two_pages = [
        _element("NarrativeText", "Solid page one text. " * 12, 1),
        _element("NarrativeText", "Solid page two text. " * 12, 2),
    ]
    bad = [_element("NarrativeText", "Tiny", 1)]

    with (
        patch("unstructured.partition.pdf.partition_pdf") as partition_pdf,
        patch.dict("os.environ", {}, clear=True),
    ):
        partition_pdf.side_effect = [bad, good_two_pages]
        _root, elements, _pages, warnings = partition(
            tmp_path / "unused.pdf", preflight=preflight
        )

    assert partition_pdf.call_count == 2
    assert partition_pdf.call_args_list[0].kwargs["strategy"] == "fast"
    assert partition_pdf.call_args_list[1].kwargs["strategy"] == "hi_res"
    assert elements
    assert any("layout-aware pass" in w for w in warnings)


def test_partition_does_not_retry_when_fast_quality_ok(tmp_path: Path) -> None:
    preflight = DocumentPreflight(
        classification="text",
        route="fast",
        confidence="high",
        num_pages=1,
    )
    good = [_element("NarrativeText", "Solid page text. " * 12, 1)]

    with (
        patch("unstructured.partition.pdf.partition_pdf") as partition_pdf,
        patch.dict("os.environ", {}, clear=True),
    ):
        partition_pdf.return_value = good
        _root, _elements, _pages, warnings = partition(
            tmp_path / "unused.pdf", preflight=preflight
        )

    partition_pdf.assert_called_once()
    assert partition_pdf.call_args.kwargs["strategy"] == "fast"
    assert warnings == []
