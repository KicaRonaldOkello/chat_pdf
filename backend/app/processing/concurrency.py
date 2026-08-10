"""Process-wide concurrency bounds for heavy pipeline work.

The worker runs several documents concurrently (``worker_concurrency``); the
semaphores below independently cap the CPU-heavy parsing/OCR/Camelot work and
the embedding calls so that parallel documents cannot saturate threads or
upstream services.
"""

from __future__ import annotations

import asyncio
import threading

_parse_lock = threading.Lock()
_embed_lock = threading.Lock()
_table_lock = threading.Lock()
_parse_sem: asyncio.Semaphore | None = None
_embed_sem: asyncio.Semaphore | None = None
_table_sem: asyncio.Semaphore | None = None


def parse_semaphore() -> asyncio.Semaphore:
    """Bound concurrent preflight/partition/Camelot work (one per event loop)."""
    global _parse_sem
    loop = asyncio.get_running_loop()
    with _parse_lock:
        if _parse_sem is None or _parse_sem._loop is not loop:
            _parse_sem = asyncio.Semaphore(_parse_limit())
    return _parse_sem


def embedding_semaphore() -> asyncio.Semaphore:
    """Bound concurrent embedding calls."""
    global _embed_sem
    loop = asyncio.get_running_loop()
    with _embed_lock:
        if _embed_sem is None or _embed_sem._loop is not loop:
            _embed_sem = asyncio.Semaphore(_embed_limit())
    return _embed_sem


def table_semaphore() -> asyncio.Semaphore:
    """Bound concurrent LLM table-description calls."""
    global _table_sem
    loop = asyncio.get_running_loop()
    with _table_lock:
        if _table_sem is None or _table_sem._loop is not loop:
            _table_sem = asyncio.Semaphore(_table_limit())
    return _table_sem


def _parse_limit() -> int:
    from app.settings import settings

    return max(1, settings.parse_concurrency)


def _embed_limit() -> int:
    from app.settings import settings

    return max(1, settings.embedding_concurrency)


def _table_limit() -> int:
    from app.settings import settings

    return max(1, settings.table_llm_concurrency)
