"""Retrieval-sufficiency judge node.

Runs *after* retrieve.  Inspects the retrieved context and decides whether
it contains enough information to answer the user's query.  If critical
terms, dates, or entities are missing, sets ``gap_query`` so the retry
loop re-enters retrieve with a refined search.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from langchain_core.messages import HumanMessage

from app.agents.journey import JourneyLogger
from app.agents.llm import create_llm
from app.agents.state import GraphState
from app.config import RETRIEVAL_MAX_RETRIES, ROUTER_MODEL

log = logging.getLogger(__name__)

# Month name to number mapping
_MONTH_TO_NUM = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_date_string(date_str: str) -> tuple[int, int, int] | None:
    """Parse a date string into (year, month, day) tuple."""
    date_str = date_str.strip()
    
    # Pattern: Full month name + year (e.g., "December 2025")
    match = re.search(r"(\w+)\s+(\d{4})", date_str, re.IGNORECASE)
    if match:
        month_name, year = match.groups()
        month = _MONTH_TO_NUM.get(month_name.lower())
        if month:
            return (int(year), month, 1)
    
    # Pattern: Abbreviated month + short year (e.g., "Dec-25")
    match = re.search(r"([A-Z][a-z]{2})-(\d{2})", date_str)
    if match:
        month_abbr, short_year = match.groups()
        month = _MONTH_TO_NUM.get(month_abbr.lower())
        if month:
            year = 2000 + int(short_year)
            return (year, month, 1)
    
    # Pattern: ISO format (e.g., "2025-12-01")
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_str)
    if match:
        year, month, day = match.groups()
        return (int(year), int(month), int(day))
    
    # Pattern: Slash format (e.g., "12/2025")
    match = re.search(r"(\d{1,2})/(\d{4})", date_str)
    if match:
        month, year = match.groups()
        return (int(year), int(month), 1)
    
    return None


def _extract_dates_from_text(text: str) -> list[tuple[int, int, int]]:
    """Extract all dates from text as (year, month, day) tuples."""
    dates = []
    
    patterns = [
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b",
        r"\b[A-Z][a-z]{2}-\d{2}\b",
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\b\d{1,2}/\d{4}\b",
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                match_str = " ".join(match)
            else:
                match_str = match
            parsed = _parse_date_string(match_str)
            if parsed:
                dates.append(parsed)
    
    return dates


def _filter_chunks_by_time_range(
    hits: list[dict[str, Any]], 
    time_range_start: str, 
    time_range_end: str
) -> list[dict[str, Any]]:
    """Filter retrieved chunks to only include those within the specified time range."""
    if not time_range_start and not time_range_end:
        return hits
    
    start_date = _parse_date_string(time_range_start) if time_range_start else None
    end_date = _parse_date_string(time_range_end) if time_range_end else None
    
    if not start_date and not end_date:
        return hits
    
    filtered = []
    for hit in hits:
        text = hit.get("display_text", "") + " " + hit.get("text_for_embedding", "")
        chunk_dates = _extract_dates_from_text(text)
        
        if not chunk_dates:
            # No dates in chunk, include it (might be relevant context)
            filtered.append(hit)
            continue
        
        # Check if any date in chunk falls within range
        chunk_in_range = False
        for chunk_date in chunk_dates:
            if start_date and end_date:
                if start_date <= chunk_date <= end_date:
                    chunk_in_range = True
                    break
            elif start_date:
                if chunk_date >= start_date:
                    chunk_in_range = True
                    break
            elif end_date:
                if chunk_date <= end_date:
                    chunk_in_range = True
                    break
        
        if chunk_in_range:
            filtered.append(hit)
    
    return filtered if filtered else hits


def _filter_chunks_by_entities(
    hits: list[dict[str, Any]], 
    key_entities: list[str]
) -> list[dict[str, Any]]:
    """Filter retrieved chunks to only include those containing key entities."""
    if not key_entities:
        return hits
    
    filtered = []
    for hit in hits:
        text = (hit.get("display_text", "") + " " + 
                hit.get("text_for_embedding", "") + " " + 
                " ".join(hit.get("keywords", []))).lower()
        
        # Check if any key entity is present (case-insensitive)
        entity_present = any(entity.lower() in text for entity in key_entities)
        if entity_present:
            filtered.append(hit)
    
    return filtered if filtered else hits


def _filter_chunks_by_sections(
    hits: list[dict[str, Any]], 
    target_sections: list[str]
) -> list[dict[str, Any]]:
    """Filter retrieved chunks to only include those from target sections."""
    if not target_sections:
        return hits
    
    filtered = []
    for hit in hits:
        section_id = hit.get("id", "")
        section_path = hit.get("section_path", "")
        
        # Check if chunk matches any target section
        section_match = any(
            target in section_id or target in section_path
            for target in target_sections
        )
        if section_match:
            filtered.append(hit)
    
    return filtered if filtered else hits

_JUDGE_PROMPT = """\
You are checking whether retrieved document excerpts contain the information
needed to answer a user's query.

User query: {query}

Retrieved excerpts (summaries):
{summaries}

Do these excerpts contain enough information to answer the query?
Return STRICT JSON:
{{"sufficient": true|false, "missing": ["term1", "term2"], "gap_query": "rewritten search query to fill gaps, or empty string"}}

Rules:
- sufficient=false ONLY when critical terms, dates, or named entities from
  the query are completely absent from ALL excerpts.
- "missing" lists the key terms that are absent.
- "gap_query" is a specific, targeted search string to find the missing
  information.

CRITICAL: Check for terminology and format mismatches across domains:
- Date formats: If the query uses "December 2025" but excerpts show "Dec-25",
  check if BOTH formats are present. When generating gap_query, try multiple formats:
  * "December 2025" → ["Dec-25", "Dec 2025", "12/2025", "12-25"]
  * Apply this pattern to any date in the query.

- Domain-specific codes and identifiers:
  * Medical: If query uses "hypertension" but excerpts show "I10", include both in gap_query
  * Legal: If query uses "Brown v. Board" but excerpts show "347 U.S. 483", include both
  * Technical: If query uses "fuel pump" but excerpts show "FP-1234", include both
  * Financial: If query uses "lending rate" but excerpts show "I_BA_UGX_L", include both

- When generating gap_query, analyze the terminology patterns in the retrieved
  excerpts and match that pattern. If excerpts use codes/abbreviations, use those
  in the gap_query. If excerpts use full names, use those.

- A single matching excerpt makes the answer sufficient.
- If the query asks about a range or trend and both endpoints are present,
  mark sufficient=true."""


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
    max_attempts = max(1, RETRIEVAL_MAX_RETRIES)

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
        filtered = _filter_chunks_by_time_range(list(hits), time_start, time_end)
        if len(filtered) < len(hits):
            logger.log_info(f"Time filter: {len(hits)} → {len(filtered)} chunks")
        hits = filtered

    # Apply entity filter if the router extracted key entities
    if key_entities:
        entity_hits = _filter_chunks_by_entities(list(hits), key_entities)
        if len(entity_hits) < len(hits):
            logger.log_info(f"Entity filter: {len(hits)} → {len(entity_hits)} chunks")
        hits = entity_hits

    # Apply section filter if the router specified target sections
    if target_sections:
        section_hits = _filter_chunks_by_sections(list(hits), target_sections)
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
        llm = create_llm(ROUTER_MODEL, temperature=0.0)
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
