from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.settings import settings

log = logging.getLogger(__name__)


class CrossEncoderCache:
    def __init__(self) -> None:
        self.value: Any = None

    def get(self) -> Any:
        if self.value is None:
            from sentence_transformers import CrossEncoder

            self.value = CrossEncoder(settings.rerank_model)
        return self.value


cache = CrossEncoderCache()

# Preload the cross-encoder at import time so the first query doesn't
# pay the cold-start cost.  The model is ~100 MB and loads in <1 s on
# modern hardware, but initialising it synchronously avoids the
# sentence-transformers logging noise during the first request.
try:
    cache.get()
    log.info("rerank model loaded: %s", settings.rerank_model)
except Exception:
    log.warning("rerank model preload failed; will retry on first query")


def passage_for_pair(h: dict[str, Any]) -> str:
    t = h.get("display_text") or h.get("text_for_embedding") or ""
    s = (t or "").strip()
    return s[:8000] if s else " "


async def rerank_hits(
    query: str,
    hits: list[dict[str, Any]],
    top_k: int,
    num_docs_in_scope: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    if not settings.rerank_enabled or not hits:
        return hits[:top_k], None
    if settings.rerank_only_multiple and num_docs_in_scope < 2:
        return hits[:top_k], None
    try:
        model = cache.get()
    except Exception as e:
        log.warning("rerank model load failed: %s", e)
        return hits[:top_k], {"applied": False, "error": str(e)}

    pairs: list[list[str]] = [[query, passage_for_pair(h)] for h in hits]

    def run_predict() -> Any:
        return model.predict(
            pairs, batch_size=settings.rerank_batch_size, show_progress_bar=False
        )

    try:
        scores = await asyncio.to_thread(run_predict)
    except Exception as e:
        log.warning("rerank predict failed: %s", e)
        return hits[:top_k], {"applied": False, "error": str(e)}

    if len(scores) != len(hits):
        return hits[:top_k], {"applied": False, "error": "score count mismatch"}
    for h, s in zip(hits, scores, strict=True):
        h["rerank_score"] = float(s)
    order = sorted(
        range(len(hits)),
        key=lambda i: float(scores[i]),
        reverse=True,
    )
    out = [hits[i] for i in order[:top_k]]
    return out, {"applied": True, "model": settings.rerank_model, "candidates": len(hits)}
