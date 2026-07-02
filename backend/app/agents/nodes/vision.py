"""On-demand visual analysis node.

Runs *after* retrieval.  When the router plan signals ``needs_vision``
or retrieved chunks include highly-ranked unanalysed image placeholders,
this node renders candidate pages and calls the vision model with a
question-specific prompt.  Results are appended to the context string
that the answerer sees.

Candidate pages are always resolved to ``(document_id, page)`` pairs
so that multi-document chats never analyse the wrong PDF.  In
single-document mode the router's ``vision_pages`` hint is trusted; in
multi-document mode only namespaced pages from retrieved image chunks
are used.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.agents.state import GraphState
from app.config import IMAGE_AUTO_VISION_SCORE
from app.processing.images import analyze_page_for_query
from app.processing import vision_cache

log = logging.getLogger(__name__)

_MAX_VISION_PAGES = 3  # hard cap — avoid blowing the context budget

# Type alias: (document_id, page_number)
_DocPage = tuple[str, int]


def _collect_candidates(state: GraphState) -> list[_DocPage]:
    """Return ``[(document_id, page), ...]`` pairs for visual analysis.

    Every pair is namespaced — even in multi-document chats we know
    exactly which PDF to render.
    """
    candidates: list[_DocPage] = []
    seen: set[tuple[str, int]] = set()

    doc_ids = state.get("document_ids") or []
    if not doc_ids and state.get("document_id"):
        doc_ids = [state["document_id"]]
    multi_doc = len(doc_ids) > 1

    # 1. Router-supplied pages — only used in single-document chats where
    #    the page number is unambiguous.  In multi-doc mode these are
    #    un-namespaced and could refer to the wrong PDF, so we skip them.
    if not multi_doc and doc_ids:
        primary = doc_ids[0]
        plan = state.get("plan") or {}
        for p in plan.get("vision_pages", []):
            try:
                pair = (primary, int(p))
                if pair not in seen:
                    candidates.append(pair)
                    seen.add(pair)
            except (TypeError, ValueError):
                pass

    # 2. Retrieved image chunks — already carry their document_id, so
    #    they are safe to use in both single- and multi-document mode.
    for hit in state.get("retrieved") or []:
        if hit.get("type") != "image":
            continue
        if hit.get("vision_analyzed", False):
            continue
        score = float(hit.get("rerank_score", hit.get("_score", 0)) or 0)
        if score < IMAGE_AUTO_VISION_SCORE:
            continue
        did = str(hit.get("document_id", ""))
        p = hit.get("page")
        if not did or not isinstance(p, int) or p <= 0:
            continue
        pair = (did, p)
        if pair not in seen:
            candidates.append(pair)
            seen.add(pair)

    return candidates


async def run(state: GraphState) -> dict[str, Any]:
    t0 = time.time()
    candidates = _collect_candidates(state)

    if not candidates:
        return {}

    # Cap total pages analysed to limit latency
    candidates = candidates[:_MAX_VISION_PAGES]

    query = state.get("query") or ""
    analyses: list[tuple[str, str, int]] = []  # (doc_id, text, page)

    for doc_id, page in candidates:
        cached = vision_cache.get(doc_id, page, query)
        if cached:
            log.info("vision: cache hit for %s p.%d", doc_id[:8], page)
            analyses.append((doc_id, cached, page))
            continue

        log.info("vision: analysing %s p.%d for query=%r", doc_id[:8], page, query[:80])
        try:
            analysis = await analyze_page_for_query(doc_id, page, query)
        except Exception:
            log.exception("vision analysis failed for %s p.%d", doc_id[:8], page)
            analysis = None
        if analysis:
            analyses.append((doc_id, analysis, page))
            try:
                vision_cache.put(doc_id, page, query, analysis)
            except Exception:
                log.debug("vision cache write failed for %s p.%d", doc_id[:8], page, exc_info=True)

    if not analyses:
        return {}

    # Append vision analysis to the existing context
    current_context = state.get("context") or ""
    vision_block = "\n\n".join(text for _, text, _ in analyses)
    new_context = f"{current_context}\n\n{vision_block}"

    # Inject visual_analysis entries *alongside* existing retrieved sources.
    # GraphState.retrieved has no reducer, so we must merge manually.
    existing_retrieved: list[dict[str, Any]] = list(state.get("retrieved") or [])
    for doc_id, analysis_text, page in analyses:
        existing_retrieved.append(
            {
                "document_id": doc_id,
                "chunk_id": f"vision:{doc_id[:8]}:p{page}",
                "section_path": f"Visual analysis — p.{page}",
                "page": page,
                "type": "visual_analysis",
                "score": 1.0,
                "display_text": analysis_text[:240],
            }
        )

    pages_analyzed = sorted(set(p for _, _, p in analyses))
    step = {
        "node": "vision",
        "duration_ms": int((time.time() - t0) * 1000),
        "output": {
            "pages_analyzed": pages_analyzed,
            "documents_analyzed": sorted(set(d for d, _, _ in analyses)),
            "analyses": len(analyses),
        },
    }
    return {
        "context": new_context,
        "retrieved": existing_retrieved,
        "trace": [step],
    }
