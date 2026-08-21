"""Library display-status mapping for uploaded documents."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.api.routes.documents import _store_display_for_uploaded


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw", "expected_display"),
    [
        ("ready", "analyzed"),
        ("partial", "analyzed"),  # usable document — must never render as error
        ("processing", "processing"),
        ("queued", "processing"),
        ("error", "error"),
        ("failed", "error"),
        ("invalid", "error"),
        ("parser_failure", "error"),
    ],
)
async def test_display_status_mapping(raw: str, expected_display: str) -> None:
    with patch(
        "app.api.routes.documents.document_data.get_status",
        return_value=SimpleNamespace(status=raw),
    ):
        processing, display = await _store_display_for_uploaded("doc-1")

    assert processing == raw
    assert display == expected_display
