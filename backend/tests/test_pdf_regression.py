"""PDF regression suite — representative documents, deterministic checks.

Mirrors the benchmark corpus (text, academic, tables, scanned, mixed, vector
charts, corrupt, encrypted) and asserts routing, page-level citation
accuracy, and chunk output without external services.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.processing import chunking, preflight, structure
from benchmarks.run_benchmark import (
    build_academic,
    build_corrupt,
    build_encrypted,
    build_financial_tables,
    build_mixed,
    build_scanned,
    build_text_report,
    build_vector_chart,
)


def _chunks_for(path: Path) -> tuple[object, list[chunking.Chunk]]:
    pf = preflight.classify_pdf(path)
    root, _elements, _pages, _warnings = structure.partition(path, preflight=pf)
    return pf, chunking.build_chunks(root, "regression")


def test_text_report_routes_fast_with_page_accurate_chunks(tmp_path: Path) -> None:
    path = build_text_report(tmp_path)
    pf, chunks = _chunks_for(path)
    assert pf.route == "fast"
    assert {c.page for c in chunks} == {1, 2, 3}

    inflation = next(c for c in chunks if "inflation" in c.display_text.lower())
    revenue = next(c for c in chunks if "Revenue" in c.display_text)
    assert inflation.page == 2
    assert revenue.page == 1


def test_academic_document_routes_fast_and_keeps_pages(tmp_path: Path) -> None:
    path = build_academic(tmp_path)
    pf, chunks = _chunks_for(path)
    assert pf.route == "fast"
    assert {c.page for c in chunks} == {1, 2}


def test_financial_table_page_produces_table_content(tmp_path: Path) -> None:
    path = build_financial_tables(tmp_path)
    pf, chunks = _chunks_for(path)
    assert pf.route == "fast"
    blob = " ".join(c.display_text for c in chunks)
    assert "Revenue" in blob
    assert "Asia" in blob
    assert all(c.page == 1 for c in chunks)


def test_scanned_pdf_routes_hi_res(tmp_path: Path) -> None:
    path = build_scanned(tmp_path)
    pf = preflight.classify_pdf(path)
    assert pf.route == "hi_res"
    assert pf.ocr_pages


def test_mixed_pdf_routes_hi_res_and_extracts_text(tmp_path: Path) -> None:
    path = build_mixed(tmp_path)
    pf, chunks = _chunks_for(path)
    assert pf.route == "hi_res"
    assert any("cover" in c.display_text.lower() for c in chunks)


def test_vector_chart_page_is_visual_candidate(tmp_path: Path) -> None:
    from app.processing.images import detect_vector_visual_pages

    path = build_vector_chart(tmp_path)
    assert detect_vector_visual_pages(path) == [1]
    pf, chunks = _chunks_for(path)
    assert pf.route == "fast"
    assert any("sales" in c.display_text.lower() for c in chunks)


def test_corrupt_pdf_terminates_as_invalid(tmp_path: Path) -> None:
    path = build_corrupt(tmp_path)
    with pytest.raises(preflight.PreflightError) as exc:
        preflight.classify_pdf(path)
    assert exc.value.status == "invalid"


def test_encrypted_pdf_terminates_as_encrypted(tmp_path: Path) -> None:
    path = build_encrypted(tmp_path)
    with pytest.raises(preflight.PreflightError) as exc:
        preflight.classify_pdf(path)
    assert exc.value.status == "encrypted"
