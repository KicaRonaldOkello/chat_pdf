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


def retry_delay(attempt: int) -> float:
    """Exponential backoff: base * 2^(attempt-1)."""
    return settings.worker_retry_base_seconds * (2 ** max(0, attempt - 1))


async def run_worker_once(
    repo: DocumentStateRepository,
    *,
    processor: ProcessorFn = process_document,
) -> RunOutcome | None:
    """Claim one due document and process it, applying the retry policy.

    Returns the outcome when a document was processed, ``None`` when the queue
    was empty.  The caller owns the transaction (commits/releases).
    """
    row = await repo.claim_next(lease_seconds=settings.worker_claim_timeout_seconds)
    if row is None:
        return None

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


async def run_worker(
    *,
    stop_event: asyncio.Event | None = None,
    processor: ProcessorFn = process_document,
) -> None:
    """Poll loop with bounded document concurrency and startup recovery."""
    from app.document_data import document_db_session

    stop = stop_event or asyncio.Event()
    sem = asyncio.Semaphore(max(1, settings.worker_concurrency))

    # Startup recovery: never leave documents stranded in extracting/tables/…
    async with document_db_session() as (session, repo):
        await recover_stale(repo)
        await session.commit()

    while not stop.is_set():
        processed_any = False
        try:
            async with document_db_session() as (session, repo):
                await repo.expire_stale_leases(
                    lease_seconds=settings.worker_claim_timeout_seconds
                )
                await session.commit()

                async def _process_one() -> bool:
                    async with (
                        sem,
                        document_db_session() as (proc_session, proc_repo),
                    ):
                        try:
                            outcome = await run_worker_once(
                                proc_repo, processor=processor
                            )
                            await proc_session.commit()
                        except Exception:
                            await proc_session.rollback()
                            raise
                        return outcome is not None

                processed_any = await _process_one()
        except Exception:
            log.exception("worker: poll cycle failed; continuing")

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
