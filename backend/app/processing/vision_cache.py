"""File-based cache for on-demand vision analysis results.

Each entry is stored as a small JSON file under the document directory.
The cache key is ``(document_id, page, query_prefix)`` — identical or very
similar queries for the same page hit the same cache entry, avoiding
redundant and expensive vision-model calls.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

from app.config import DOCUMENTS_DIR, VISION_MODEL

log = logging.getLogger(__name__)

_CACHE_SUBDIR = "vision_cache"
# Bump this when QA_VISION_PROMPT changes — prevents stale cached results
# from being reused after a prompt update.
_PROMPT_VERSION = "v1"


def _cache_dir(doc_id: str) -> Path:
    return DOCUMENTS_DIR / doc_id / _CACHE_SUBDIR


def _cache_key(
    doc_id: str, page: int, query: str, *, model: str | None = None
) -> str:
    """Build a stable cache key from doc, page, query, model, and prompt version.

    Changing the model or prompt version produces a different key so stale
    analysis is never served after a configuration change.
    """
    model_name = (model or VISION_MODEL).strip()
    # Use first 120 chars of the query — long enough to disambiguate,
    # short enough to avoid filesystem issues.
    prefix = query.strip()[:120].lower()
    composite = f"{model_name}|{_PROMPT_VERSION}|{prefix}"
    h = hashlib.sha256(composite.encode()).hexdigest()[:16]
    return f"p{page:04d}_{h}.json"


def _cache_path(doc_id: str, page: int, query: str) -> Path:
    return _cache_dir(doc_id) / _cache_key(doc_id, page, query)


def get(doc_id: str, page: int, query: str) -> str | None:
    """Return a cached analysis for *page* and *query*, or ``None``."""
    path = _cache_path(doc_id, page, query)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        analysis = data.get("analysis")
        if isinstance(analysis, str) and analysis.strip():
            age_s = time.time() - data.get("cached_at", 0)
            log.debug("vision cache hit: %s (age=%.0fs)", path.name, age_s)
            return analysis.strip()
    except Exception:
        log.debug("vision cache read failed for %s", path.name, exc_info=True)
    return None


def put(doc_id: str, page: int, query: str, analysis: str) -> None:
    """Store a vision analysis result."""
    path = _cache_path(doc_id, page, query)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "document_id": doc_id,
        "page": page,
        "query_prefix": query.strip()[:120],
        "analysis": analysis,
        "cached_at": time.time(),
    }
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    log.debug("vision cache write: %s", path.name)


def clear_for_document(doc_id: str) -> int:
    """Delete all cached vision entries for *doc_id*.  Returns count removed."""
    d = _cache_dir(doc_id)
    if not d.exists():
        return 0
    removed = 0
    for p in d.iterdir():
        if p.is_file():
            p.unlink()
            removed += 1
    if removed:
        try:
            d.rmdir()
        except OSError:
            pass
    return removed
