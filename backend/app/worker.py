"""Durable ingestion worker.

Polls ``document_state`` (Postgres) for queued documents, processes them with
bounded concurrency, retries retryable failures with exponential backoff, and
recovers documents stranded in intermediate states after a crash or restart.

Run separately from the API: ``python -m app.worker`` (or the container
command override).
"""

from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable

from app.db.repositories.document_state import DocumentStateRepository
from app.processing.pipeline import (
    RETRYABLE_STATUSES,
    RunOutcome,
    process_document,
)
from app.settings import settings

log = logging.getLogger(__name__)

ProcessorFn = Callable[[str, int], Awaitable[RunOutcome]]


class QueueSchemaError(RuntimeError):
    """Raised when the worker-queue columns are missing (migration not run)."""


def retry_delay(attempt: int) -> float:
    """Exponential backoff: base * 2^(attempt-1)."""
    return settings.worker_retry_base_seconds * (2 ** max(0, attempt - 1))


async def run_worker_once(
    repo: DocumentStateRepository,
    *,
    processor: ProcessorFn = process_document,
    commit: Callable[[], Awaitable[None]] | None = None,
) -> RunOutcome | None:
    """Claim one due document and process it, applying the retry policy.

    Returns the outcome when a document was processed, ``None`` when the queue
    was empty.  ``commit`` is awaited right after claiming so the row lock is
    released before processing starts — otherwise ``process_document``'s
    status writes block on the same row and the document looks stuck in
    ``queued`` until the whole run finishes.
    """
    row = await repo.claim_next(lease_seconds=settings.worker_claim_timeout_seconds)
    if row is None:
        return None
    if commit is not None:
        await commit()

    doc_id = row.document_id
    attempt = max(1, (row.attempts or 0) + 1)
    log.info("worker: processing %s (attempt %d)", doc_id, attempt)
    try:
        outcome = await processor(doc_id, attempt)
        if outcome.status in ("ready", "partial", "invalid", "encrypted", "unknown"):
            await repo.release_claim(doc_id)
            return outcome
        if (
            outcome.status in RETRYABLE_STATUSES
            and attempt < settings.worker_max_attempts
        ):
            delay = retry_delay(attempt)
            log.warning(
                "worker: %s failed retryably (%s); retrying in %.0fs",
                doc_id,
                outcome.status,
                delay,
            )
            await repo.schedule_retry(doc_id, delay_seconds=delay)
            return outcome
        log.error(
            "worker: %s failed terminally (%s) after %d attempt(s); marking failed",
            doc_id,
            outcome.status,
            attempt,
        )
        await repo.mark_failed(doc_id, outcome.status, outcome.error)
        return outcome
    except Exception as exc:  # pragma: no cover - processor is expected to catch
        log.exception("worker: unexpected failure processing %s", doc_id)
        if attempt < settings.worker_max_attempts:
            delay = retry_delay(attempt)
            await repo.schedule_retry(doc_id, delay_seconds=delay)
        else:
            await repo.mark_failed(doc_id, "parser_failure", str(exc))
        return RunOutcome(status="parser_failure", retryable=True, error=str(exc))


async def recover_stale(repo: DocumentStateRepository) -> int:
    """Reset expired in-flight rows to ``queued``; return how many."""
    recovered = await repo.recover_stale(
        lease_seconds=settings.worker_claim_timeout_seconds
    )
    if recovered:
        log.info(
            "worker: recovered %d stale document(s): %s", len(recovered), recovered
        )
    return len(recovered)


async def _check_queue_schema(repo: DocumentStateRepository) -> None:
    """Fail fast with an actionable message when the queue columns are missing.

    The worker depends on the ``document_state.attempts`` /
    ``next_attempt_at`` / ``claimed_until`` columns added by migration 0008.
    Without them every poll cycle errors and documents stay ``queued``
    forever, so detect this once at startup instead of silently retrying.
    """
    try:
        await repo.claim_next(lease_seconds=1)
    except Exception as exc:
        msg = str(exc).lower()
        if "column" in msg and ("does not exist" in msg or "no such column" in msg):
            raise QueueSchemaError(
                "Worker queue columns are missing from document_state. "
                "Run the database migration first: "
                "`alembic upgrade head` (the deploy workflow runs "
                "`docker exec chat_pdf_api alembic upgrade head`). "
                f"Underlying error: {exc}"
            ) from exc
        raise


async def run_worker(
    *,
    stop_event: asyncio.Event | None = None,
    processor: ProcessorFn = process_document,
) -> None:
    """Poll loop with bounded document concurrency and startup recovery.

    Up to ``worker_concurrency`` documents are processed concurrently: the
    loop keeps that many claim tasks in flight, so a slow document (or a
    slow background enrichment) never blocks new uploads from being claimed.
    """
    from app.document_data import document_db_session

    stop = stop_event or asyncio.Event()
    concurrency = max(1, settings.worker_concurrency)
    sem = asyncio.Semaphore(concurrency)

    # Startup recovery: never leave documents stranded in extracting/tables/…
    async with document_db_session() as (session, repo):
        await _check_queue_schema(repo)
        await recover_stale(repo)
        await session.commit()

    async def _process_one() -> bool:
        async with sem:
            async with document_db_session() as (session, repo):
                try:
                    outcome = await run_worker_once(
                        repo,
                        processor=processor,
                        commit=session.commit,
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise
                return outcome is not None

    pending: set[asyncio.Task[bool]] = set()

    while not stop.is_set():
        processed_any = False

        # Reap finished tasks; surface unexpected failures.
        for task in list(pending):
            if not task.done():
                continue
            pending.discard(task)
            try:
                processed_any = processed_any or task.result()
            except Exception:
                log.exception("worker: document task failed; continuing")

        # Expire stale leases once per cycle (safety net for dead workers).
        try:
            async with document_db_session() as (session, repo):
                await repo.expire_stale_leases(
                    lease_seconds=settings.worker_claim_timeout_seconds
                )
                await session.commit()
        except Exception:
            log.exception("worker: poll cycle failed; continuing")

        # Keep up to `concurrency` documents in flight.
        while len(pending) < concurrency and not stop.is_set():
            pending.add(asyncio.create_task(_process_one()))

        if not processed_any or stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=settings.worker_poll_interval_seconds
                )
            except TimeoutError:
                pass


def _install_signal_handlers(
    loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event
) -> None:
    def _request_stop() -> None:
        log.info("worker: shutdown requested; draining")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda *_: _request_stop())


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-40s  %(levelname)-8s  %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("app.processing").setLevel(logging.INFO)

    import app.runtime as app_runtime
    from app.db import open_db_engine
    from app.settings import settings as _settings

    if not _settings.database_url:
        raise RuntimeError("DATABASE_URL is required to run the worker")

    async def _run() -> None:
        opened = await open_db_engine()
        if opened is None:
            raise RuntimeError("Failed to open the database engine")
        engine, session_maker = opened
        app_runtime.db_session_maker = session_maker
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        _install_signal_handlers(loop, stop_event)
        try:
            # The GitHub Actions deploy brings up api+worker before applying
            # migrations, so the queue columns may not exist for a few
            # seconds.  Retry startup recovery until the schema is ready.
            deadline = _settings.worker_claim_timeout_seconds
            waited = 0.0
            while True:
                try:
                    await run_worker(stop_event=stop_event)
                    break
                except QueueSchemaError as exc:
                    raise SystemExit(str(exc)) from exc
                except Exception as exc:
                    if waited >= deadline or stop_event.is_set():
                        raise
                    log.warning(
                        "worker: startup failed (%s); retrying in %ds (waited %.0fs)",
                        exc,
                        _settings.worker_poll_interval_seconds,
                        waited,
                    )
                    await asyncio.sleep(_settings.worker_poll_interval_seconds)
                    waited += _settings.worker_poll_interval_seconds
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        log.info("worker: stopped")


if __name__ == "__main__":
    main()
