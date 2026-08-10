"""Worker-queue repository primitives (claim / retry / fail / recover)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.models.document_state import DocumentState
from app.db.repositories.document_state import DocumentStateRepository


def _row(doc_id: str, status: str) -> DocumentState:
    return DocumentState(
        document_id=doc_id,
        status_payload={"status": status, "stage": status},
        attempts=0,
    )


def _session_with_row(row: DocumentState | None) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=row)
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_claim_next_uses_skip_locked_and_sets_lease() -> None:
    row = _row("doc-1", "queued")
    repo = DocumentStateRepository(_session_with_row(row))

    now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
    claimed = await repo.claim_next(lease_seconds=3600, now=now)

    assert claimed is row
    assert row.claimed_until == now + timedelta(seconds=3600)


@pytest.mark.asyncio
async def test_claim_next_returns_none_when_empty() -> None:
    repo = DocumentStateRepository(_session_with_row(None))
    assert await repo.claim_next(lease_seconds=3600) is None


@pytest.mark.asyncio
async def test_mark_failed_sets_status_and_clears_claim() -> None:
    row = _row("doc-1", "parser_failure")
    row.claimed_until = datetime.now(UTC)
    repo = DocumentStateRepository(_session_with_row(row))

    await repo.mark_failed("doc-1", "parser_failure", "boom")

    assert row.status_payload["status"] == "failed"
    assert "parser_failure" in row.status_payload["stage"]
    assert row.status_payload["error"] == "boom"
    assert row.attempts == 1
    assert row.claimed_until is None
    assert row.next_attempt_at is None


@pytest.mark.asyncio
async def test_schedule_retry_resets_to_queued_with_backoff() -> None:
    row = _row("doc-1", "parser_failure")
    repo = DocumentStateRepository(_session_with_row(row))
    now = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

    await repo.schedule_retry("doc-1", delay_seconds=120, now=now)

    assert row.status_payload["status"] == "queued"
    assert row.attempts == 1
    assert row.next_attempt_at == now + timedelta(seconds=120)
    assert row.claimed_until is None
