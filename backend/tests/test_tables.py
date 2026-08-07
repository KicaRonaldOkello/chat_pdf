"""Selective/observable table handling tests (synthetic PDFs + mocks)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest

from app.processing.tables import (
    TableDiagnostics,
    describe_one,
    detect_table_pages,
    extract_tables,
)
from app.settings import settings


def _pdf_with_table_page(tmp_path: Path, name: str = "tables.pdf") -> Path:
    path = tmp_path / name
    doc = fitz.open()
    page = doc.new_page()
    rows = [
        "| Country | Pop | GDP |",
        "|---------|-----|-----|",
        "| Kenya | 54M | 113B |",
        "| Uganda | 47M | 49B |",
        "| Rwanda | 14M | 13B |",
    ]
    page.insert_text((72, 72), "\n".join(rows), fontsize=10)
    page2 = doc.new_page()
    page2.insert_text(
        (72, 72), "This is a normal prose page with no tables.", fontsize=11
    )
    doc.save(path)
    doc.close()
    return path


def test_detect_table_pages_finds_pipe_rich_page(tmp_path: Path) -> None:
    path = _pdf_with_table_page(tmp_path)

    pages, diag = detect_table_pages(path)

    assert diag.total_pages == 2
    assert pages == [1]
    assert diag.pages_skipped == [2]


def test_detect_table_pages_returns_empty_for_prose_only(tmp_path: Path) -> None:
    path = tmp_path / "prose.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Just prose. " * 60, fontsize=11)
    doc.save(path)
    doc.close()

    pages, diag = detect_table_pages(path)

    assert pages == []
    assert diag.pages_skipped == [1]


def test_extract_tables_skips_camelot_when_no_pages_detected(
    tmp_path: Path,
) -> None:
    path = _pdf_with_table_page(tmp_path)
    diag = TableDiagnostics()

    with (
        patch("app.processing.tables.detect_table_pages", return_value=([], diag)),
        patch("camelot.read_pdf") as read_pdf,
    ):
        tables = extract_tables(path, diag)

    assert tables == []
    read_pdf.assert_not_called()
    assert diag.pages_detected == []


def test_extract_tables_records_lattice_failure(tmp_path: Path) -> None:
    path = _pdf_with_table_page(tmp_path)
    diag = TableDiagnostics()

    with (
        patch(
            "app.processing.tables.detect_table_pages",
            return_value=([1, 2], diag),
        ),
        patch(
            "camelot.read_pdf",
            side_effect=RuntimeError("camelot boom"),
        ),
    ):
        tables = extract_tables(path, diag)

    assert tables == []
    assert any("lattice extraction failed" in err for err in diag.errors)


@pytest.mark.asyncio
async def test_describe_one_retries_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "table_describer_max_retries", 2)
    monkeypatch.setattr(settings, "table_describer_retry_base_seconds", 0.0)

    calls = {"n": 0}

    async def _create(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("upstream down")
        msg = MagicMock()
        msg.message.content = "A table of countries."
        resp = MagicMock()
        resp.choices = [msg]
        return resp

    fake_client = MagicMock()
    fake_client.chat.completions.create = _create

    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await describe_one("| A | B |\n|---|---|\n| 1 | 2 |")

    assert result == "A table of countries."
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_describe_one_returns_empty_after_exhausting_retries(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "table_describer_max_retries", 1)
    monkeypatch.setattr(settings, "table_describer_retry_base_seconds", 0.0)

    calls = {"n": 0}

    async def _create(**kwargs):
        calls["n"] += 1
        raise RuntimeError("upstream down")

    fake_client = MagicMock()
    fake_client.chat.completions.create = _create

    with patch("openai.AsyncOpenAI", return_value=fake_client):
        result = await describe_one("| A |\n|---|\n| 1 |")

    assert result == ""
    assert calls["n"] == 2
