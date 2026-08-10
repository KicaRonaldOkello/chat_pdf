"""Readiness gating: partial documents are chat/search-usable."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.api.documents import readiness_error_for_documents
from app.db.repositories.document_state import DocumentStatus


@pytest.mark.asyncio
async def test_partial_document_is_ready_for_chat() -> None:
    status = DocumentStatus(
        status="partial",
        stage="ready",
        progress=1.0,
        filename="POE-2026-06-JUN.pdf",
        warnings=["1 of 40 pages had no usable text."],
    )
    with patch(
        "app.api.documents.document_data.get_status", new_callable=AsyncMock
    ) as gs:
        gs.return_value = status
        error = await readiness_error_for_documents(["doc-1"])
    assert error is None


@pytest.mark.asyncio
async def test_queued_document_still_blocks_chat() -> None:
    status = DocumentStatus(
        status="queued",
        stage="queued",
        progress=0.0,
        filename="a.pdf",
    )
    with patch(
        "app.api.documents.document_data.get_status", new_callable=AsyncMock
    ) as gs:
        gs.return_value = status
        error = await readiness_error_for_documents(["doc-1"])
    assert error is not None
    assert "not ready" in error
