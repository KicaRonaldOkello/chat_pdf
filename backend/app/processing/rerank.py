from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import (
    RERANK_BATCH_SIZE,
    RERANK_ENABLED,
    RERANK_MODEL,
    RERANK_ONLY_MULTIPLE,
)

log = logging.getLogger(__name__)


class CrossEncoderCache:
    def __init__(self) -> None:
        self.value: Any = None

    def get(self) -> Any:
        if self.value is None:
            from sentence_transformers import CrossEncoder

            self.value = CrossEncoder(RERANK_MODEL)
        return self.value


cache = CrossEncoderCache()


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
    if not RERANK_ENABLED or not hits:
        return hits[:top_k], None
    if RERANK_ONLY_MULTIPLE and num_docs_in_scope < 2:
        return hits[:top_k], None
    try:
        model = cache.get()
    except Exception as e:
        log.warning("rerank model load failed: %s", e)
        return hits[:top_k], {"applied": False, "error": str(e)}

    pairs: list[list[str]] = [[query, passage_for_pair(h)] for h in hits]

    def run_predict() -> Any:
        return model.predict(
            pairs, batch_size=RERANK_BATCH_SIZE, show_progress_bar=False
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
    return out, {"applied": True, "model": RERANK_MODEL, "candidates": len(hits)}
