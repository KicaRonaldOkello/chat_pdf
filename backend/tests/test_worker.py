"""Worker queue logic tests (mocked repo + processor)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.processing.pipeline import RunOutcome
from app.settings import settings
from app.worker import retry_delay, run_worker, run_worker_once


def _row(doc_id: str = "doc-1", attempts: int = 0) -> SimpleNamespace:
    return SimpleNamespace(document_id=doc_id, attempts=attempts)


def _repo() -> MagicMock:
    repo = MagicMock()
    repo.claim_next = AsyncMock(return_value=None)
    repo.release_claim = AsyncMock()
    repo.schedule_retry = AsyncMock()
    repo.mark_failed = AsyncMock()
    return repo


def test_retry_delay_exponential() -> None:
    base = settings.worker_retry_base_seconds
    assert retry_delay(1) == base
    assert retry_delay(2) == base * 2
    assert retry_delay(3) == base * 4


async def test_run_worker_once_empty_queue_returns_none() -> None:
    repo = _repo()
    outcome = await run_worker_once(repo)
    assert outcome is None
    repo.claim_next.assert_awaited_once()


async def test_run_worker_once_commits_claim_before_processing() -> None:
    repo = _repo()
    repo.claim_next = AsyncMock(return_value=_row())
    order: list[str] = []
    commits = {"n": 0}

    async def _commit() -> None:
        commits["n"] += 1
        order.append("commit")

    async def _processor(doc_id: str, attempt: int) -> RunOutcome:
        order.append("process")
        return RunOutcome(status="ready", retryable=False)

    await run_worker_once(repo, processor=_processor, commit=_commit)

    assert order == ["commit", "process"]
    assert commits["n"] == 1
    repo.release_claim.assert_awaited_once_with("doc-1")


async def test_run_worker_once_ready_releases_claim() -> None:
    repo = _repo()
    repo.claim_next = AsyncMock(return_value=_row())

    async def _processor(doc_id: str, attempt: int) -> RunOutcome:
        assert doc_id == "doc-1"
        assert attempt == 1
        return RunOutcome(status="ready", retryable=False)

    outcome = await run_worker_once(repo, processor=_processor)

    assert outcome is not None and outcome.status == "ready"
    repo.release_claim.assert_awaited_once_with("doc-1")
    repo.schedule_retry.assert_not_awaited()
    repo.mark_failed.assert_not_awaited()


async def test_run_worker_once_retryable_schedules_backoff() -> None:
    repo = _repo()
    repo.claim_next = AsyncMock(return_value=_row())

    async def _processor(doc_id: str, attempt: int) -> RunOutcome:
        return RunOutcome(status="parser_failure", retryable=True, error="boom")

    await run_worker_once(repo, processor=_processor)

    repo.schedule_retry.assert_awaited_once()
    kwargs = repo.schedule_retry.await_args.kwargs
    assert kwargs["delay_seconds"] == retry_delay(1)
    repo.release_claim.assert_not_awaited()
    repo.mark_failed.assert_not_awaited()


async def test_run_worker_once_terminal_failure_marks_failed() -> None:
    repo = _repo()
    repo.claim_next = AsyncMock(return_value=_row(attempts=2))

    async def _processor(doc_id: str, attempt: int) -> RunOutcome:
        assert attempt == 3
        return RunOutcome(status="parser_failure", retryable=True, error="boom")

    await run_worker_once(repo, processor=_processor)

    repo.mark_failed.assert_awaited_once()
    args, _kwargs = repo.mark_failed.await_args
    assert args[0] == "doc-1"
    assert args[1] == "parser_failure"
    repo.schedule_retry.assert_not_awaited()


async def test_run_worker_once_encrypted_is_terminal_no_retry() -> None:
    repo = _repo()
    repo.claim_next = AsyncMock(return_value=_row())

    async def _processor(doc_id: str, attempt: int) -> RunOutcome:
        return RunOutcome(status="encrypted", retryable=False, error="locked")

    await run_worker_once(repo, processor=_processor)

    repo.release_claim.assert_awaited_once_with("doc-1")
    repo.schedule_retry.assert_not_awaited()
    repo.mark_failed.assert_not_awaited()


async def test_run_worker_recovery_and_poll_loop() -> None:
    repo = MagicMock()
    repo.claim_next = AsyncMock(return_value=None)
    repo.release_claim = AsyncMock()
    repo.schedule_retry = AsyncMock()
    repo.mark_failed = AsyncMock()
    repo.recover_stale = AsyncMock(return_value=["stale-1"])
    repo.expire_stale_leases = AsyncMock(return_value=0)
    repo.claim_next = AsyncMock(return_value=None)

    processed: list[tuple[str, int]] = []

    async def _processor(doc_id: str, attempt: int) -> RunOutcome:
        processed.append((doc_id, attempt))
        return RunOutcome(status="ready", retryable=False)

    stop = asyncio.Event()

    @asynccontextmanager
    async def _fake_session():
        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        yield session, repo

    async def _stop_after_first_poll() -> None:
        await asyncio.sleep(0.05)
        stop.set()

    with patch("app.document_data.document_db_session", _fake_session):
        await asyncio.wait_for(
            asyncio.gather(
                run_worker(stop_event=stop, processor=_processor),
                _stop_after_first_poll(),
            ),
            timeout=10,
        )

    repo.recover_stale.assert_awaited_once()
    repo.expire_stale_leases.assert_awaited()
    assert processed == []
