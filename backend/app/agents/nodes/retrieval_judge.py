"""Retrieval-sufficiency judge node.

Runs *after* retrieve.  Inspects the retrieved context and decides whether
it contains enough information to answer the user's query.  If critical
terms, dates, or entities are missing, sets ``gap_query`` so the retry
loop re-enters retrieve with a refined search.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from app.agents.journey import JourneyLogger
from app.agents.llm_factory import LLMConfig, get_llm
from app.agents.state import GraphState
from app.agents.utils.retrieval_utils import (
    filter_chunks_by_entities,
    filter_chunks_by_sections,
    filter_chunks_by_time_range,
)
from app.settings import settings

log = logging.getLogger(__name__)

# Month name to number mapping

_JUDGE_PROMPT = """\
Check whether retrieved excerpts contain the information needed to answer
a user's query.

User query: {query}

Retrieved excerpts (summaries):
{summaries}

Return STRICT JSON:
{{"sufficient": true|false, "missing": ["..."], "gap_query": "..."}}

Rules:
- sufficient=false ONLY when critical terms, dates, or entities are absent
  from ALL excerpts.
- "gap_query" must use the same date formats and terminology found in the
  excerpts (e.g. "Apr-25" not "April 2025"; indicator codes not prose names).
- A single matching excerpt makes the answer sufficient."""


def _build_summaries(hits: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, h in enumerate(hits[:12]):
        sp = h.get("section_path", "")[:60]
        t = h.get("type", "?")
        dt = str(h.get("display_text", ""))[:200]
        parts.append(f"[{i}] type={t} section={sp}\n  {dt}")
    return "\n\n".join(parts) if parts else "(no excerpts)"


async def run(state: GraphState) -> dict[str, Any]:
    logger = JourneyLogger("retrieval_judge")
    logger.log_start()

    query = state.get("query", "")
    hits = state.get("retrieved") or []
    attempts = state.get("retrieval_attempts", 0)
    max_attempts = max(1, settings.retrieval_max_retries)

    # Hard cap — don't loop forever
    if attempts >= max_attempts:
        logger.log_info(f"Max attempts ({max_attempts}) reached, forcing sufficient")
        journey_data = logger.log_complete({"sufficient": True, "reason": "max_attempts"})
        return {"retrieval_sufficient": True, "gap_query": "", "journey": [journey_data]}

    # Fast path: no hits at all → definitely insufficient
    if not hits:
        logger.log_info("No hits retrieved, marking insufficient")
        journey_data = logger.log_complete({"sufficient": False, "reason": "no_hits"})
        return {
            "retrieval_sufficient": False,
            "gap_query": query,
            "trace": [{"node": "retrieval_judge", "output": {"verdict": "insufficient (no hits)"}}],
            "journey": [journey_data],
        }

    # ── Deterministic pre-checks (free, no LLM call) ────────────────
    plan = state.get("plan") or {}
    key_entities: list[str] = list(plan.get("key_entities") or [])
    time_start = str(plan.get("time_range_start") or "")
    time_end = str(plan.get("time_range_end") or "")
    target_sections: list[str] = list(plan.get("target_sections") or [])

    initial_hits = len(hits)

    # Apply time-range filter if the query specifies a date range
    if time_start or time_end:
        filtered = filter_chunks_by_time_range(list(hits), time_start, time_end)
        if len(filtered) < len(hits):
            logger.log_info(f"Time filter: {len(hits)} → {len(filtered)} chunks")
        hits = filtered

    # Apply entity filter if the router extracted key entities
    if key_entities:
        entity_hits = filter_chunks_by_entities(list(hits), key_entities)
        if len(entity_hits) < len(hits):
            logger.log_info(f"Entity filter: {len(hits)} → {len(entity_hits)} chunks")
        hits = entity_hits

    # Apply section filter if the router specified target sections
    if target_sections:
        section_hits = filter_chunks_by_sections(list(hits), target_sections)
        if len(section_hits) < len(hits):
            logger.log_info(f"Section filter: {len(hits)} → {len(section_hits)} chunks")
        hits = section_hits

    # ── Deterministic entity presence check ─────────────────────────
    # If ALL key entities appear in the filtered hits AND the context is
    # small enough to trust, skip the LLM call.  For large contexts
    # (>10K chars of display text) the entities may be present but
    # buried in irrelevant rows — still run the LLM to verify.
    _total_display = sum(len(h.get("display_text", "")) for h in hits)
    _skip_llm = _total_display <= 10_000
    if key_entities and hits and _skip_llm:
        all_text = " ".join(
            h.get("display_text", "") + " " + h.get("text_for_embedding", "")
            for h in hits
        ).lower()
        found_all = all(
            entity.lower() in all_text for entity in key_entities
        )
        if found_all:
            logger.log_info(f"Deterministic pass: all {len(key_entities)} entities found")
            journey_data = logger.log_complete({
                "sufficient": True,
                "method": "deterministic",
                "entities_found": key_entities,
                "filters_applied": initial_hits != len(hits),
            })
            return {
                "retrieval_sufficient": True,
                "gap_query": "",
                "trace": [{
                    "node": "retrieval_judge",
                    "output": {
                        "verdict": "sufficient (deterministic entity match)",
                        "entities_found": key_entities,
                    },
                }],
                "journey": [journey_data],
            }

    # ── LLM sufficiency check ───────────────────────────────────────
    logger.log_info("Running LLM sufficiency check")
    summaries = _build_summaries(hits)
    prompt = _JUDGE_PROMPT.format(query=query, summaries=summaries[:3000])

    sufficient = True
    gap_query = ""
    missing: list[str] = []

    try:
        llm = get_llm(LLMConfig.ROUTER)
        structured = llm.with_structured_output(
            type(
                "RetrievalJudge",
                (object,),
                {
                    "__annotations__": {
                        "sufficient": bool,
                        "missing": list[str],
                        "gap_query": str,
                    }
                },
            ),
            method="json_mode",
        )
        result = await structured.ainvoke([HumanMessage(content=prompt)])
        sufficient = bool(getattr(result, "sufficient", True))
        gap_query = (getattr(result, "gap_query", "") or "").strip()
        missing = list(getattr(result, "missing", []) or [])

        if sufficient:
            logger.log_info("LLM: sufficient")
        else:
            logger.log_info(f"LLM: insufficient (missing: {missing[:3]})")
    except Exception as e:
        logger.log_error("LLM failed, defaulting to sufficient", e)
        log.debug("retrieval judge LLM failed; defaulting to sufficient", exc_info=True)

    if not sufficient and gap_query and attempts < max_attempts:
        logger.log_info(f"Will retry with gap_query: {gap_query[:50]}")
    else:
        sufficient = True  # force-sufficient if we're out of retries
        gap_query = ""

    journey_data = logger.log_complete({
        "sufficient": sufficient,
        "method": "llm",
        "missing": missing,
        "gap_query": gap_query,
        "filters_applied": initial_hits != len(hits),
        "filtered_count": len(hits),
        "initial_count": initial_hits,
    })

    step = {
        "node": "retrieval_judge",
        "duration_ms": journey_data["duration_ms"],
        "output": {
            "sufficient": sufficient,
            "missing": missing,
            "gap_query": gap_query,
            "attempt": attempts,
        },
    }
    return {
        "retrieval_sufficient": sufficient,
        "gap_query": gap_query,
        "trace": [step],
        "journey": [journey_data],
    }
