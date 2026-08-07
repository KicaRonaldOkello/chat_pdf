from __future__ import annotations

import logging as _logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app import document_data
from app.agents.journey import JourneyLogger
from app.agents.llm_factory import LLMConfig, get_llm
from app.agents.prompts import get_router_prompt
from app.agents.schemas import RouterPlan
from app.agents.state import GraphState
from app.agents.utils.date_utils import expand_query_variants
from app.processing.metadata import normalize_title

log = _logging.getLogger(__name__)


def scope_document_ids(state: GraphState) -> list[str]:
    if state.get("document_ids"):
        return list(state["document_ids"])
    return [state["document_id"]]


def compact_toc(
    document_id: str, entries: list[dict[str, Any]], limit: int = 20
) -> str:
    rows: list[str] = []
    for e in entries[:limit]:
        summary = (e.get("summary") or "").strip()[:200]
        kws = ", ".join((e.get("keywords") or [])[:6])
        local_id = e.get("id", "")
        full_id = f"{document_id}:{local_id}" if local_id else document_id
        rows.append(
            f"- [{full_id}] {e.get('path', e.get('title'))}  "
            f"(pp. {e['page_range'][0]}-{e['page_range'][1]})"
            + (f"\n    summary: {summary}" if summary else "")
            + (f"\n    keywords: {kws}" if kws else "")
        )
    return "\n".join(rows)


def detect_terminology_patterns(entries: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Detect terminology patterns from document sections to inform query expansion.

    Returns a dict with pattern types and examples found in the TOC:
    {
        "codes": ["I_BA_UGX_L", "I10", "FP-1234"],  # Alphanumeric codes
        "abbreviations": ["CBR", "T-bill", "ICD"],  # Common abbreviations
        "date_formats": ["Dec-25", "Apr-26"],  # Date patterns used
        "identifiers": ["347 U.S. 483", "part number 5678"],  # Other identifiers
        "entities": ["Bank of Uganda", "VAT", "lending rate"],  # Named entities
        "data_types": ["time series", "percentages", "monetary values"],  # Data types
    }
    """
    patterns: dict[str, list[str]] = {
        "codes": [],
        "abbreviations": [],
        "date_formats": [],
        "identifiers": [],
        "entities": [],
        "data_types": [],
    }

    all_text = " ".join(
        e.get("title", "")
        + " "
        + e.get("summary", "")
        + " "
        + " ".join(e.get("keywords", []))
        for e in entries
    )

    # Detect alphanumeric codes (e.g., I_BA_UGX_L, I10, FP-1234)
    code_pattern = re.compile(r"\b[A-Z]{1,3}[_-]?[A-Z0-9][A-Z0-9_-]*\b")
    patterns["codes"] = list(set(code_pattern.findall(all_text)))

    # Detect common abbreviations (2-4 uppercase letters)
    abbr_pattern = re.compile(r"\b[A-Z]{2,4}\b")
    abbrs = abbr_pattern.findall(all_text)
    # Filter out common words that aren't abbreviations
    common_words = {
        "THE",
        "AND",
        "FOR",
        "WITH",
        "FROM",
        "THIS",
        "THAT",
        "ARE",
        "WAS",
        "WERE",
    }
    patterns["abbreviations"] = [a for a in abbrs if a not in common_words]

    # Detect date formats (Dec-25, Apr-26, etc.)
    date_pattern = re.compile(r"\b[A-Z][a-z]{2}-\d{2}\b")
    patterns["date_formats"] = list(set(date_pattern.findall(all_text)))

    # Detect legal/technical identifiers (e.g., 347 U.S. 483, part number 5678)
    identifier_pattern = re.compile(
        r"\b\d+\s+[A-Z]+\s+\d+\b|\bpart\s+number\s+\w+\b", re.IGNORECASE
    )
    patterns["identifiers"] = list(set(identifier_pattern.findall(all_text)))

    # Detect data type indicators
    data_type_patterns = [
        (r"\bpercent(?:age)?\b", "percentages"),
        (r"\brate\b", "rates"),
        (r"\b(?:time\s+)?series\b", "time series"),
        (r"\bmonetary\b|\b(?:currency|money|amount|value)\b", "monetary values"),
        (r"\b(?:code|identifier)\b", "codes"),
    ]
    for pattern, dtype in data_type_patterns:
        if (
            re.search(pattern, all_text, re.IGNORECASE)
            and dtype not in patterns["data_types"]
        ):
            patterns["data_types"].append(dtype)

    # Extract entities from keywords and titles (capitalized phrases)
    entity_pattern = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")
    entities = set()
    for e in entries:
        for kw in e.get("keywords", []):
            if re.match(entity_pattern, kw):
                entities.add(kw)
        title = e.get("title", "")
        if re.match(entity_pattern, title):
            entities.add(title)
    patterns["entities"] = list(entities)[:10]  # Limit to top 10

    return patterns


def compact_meta(meta: dict[str, Any] | None) -> str:
    if not meta:
        return "(document meta unavailable)"
    bits = [
        f"doc_type: {meta.get('doc_type', '?')}",
        f"title: {meta.get('inferred_title', meta.get('filename', ''))}",
    ]
    abs_ = (meta.get("abstract") or "").strip()
    if abs_:
        bits.append(f"abstract: {abs_[:500]}")
    visual_pages = meta.get("visual_pages") or []
    if visual_pages:
        bits.append(f"visual_pages: {', '.join(str(p) for p in visual_pages[:30])}")
    return "\n".join(bits)


async def render_user(state: GraphState, *, avoid_route: str | None = None) -> str:
    doc_ids = scope_document_ids(state)
    history = state.get("history") or []
    chat = "\n".join(f"{m['role']}: {m['content']}" for m in history[-4:])
    retry_hint = (
        f"\n\nPREVIOUS ATTEMPT failed. Avoid route: {avoid_route}. "
        "Try a different strategy."
        if avoid_route
        else ""
    )
    parts: list[str] = []
    for did in doc_ids:
        entries = (await document_data.get_sections_index(did)) or []
        meta = await document_data.get_document_meta(did)
        st = await document_data.get_status(did)
        label = st.filename if st and st.filename else did
        patterns = detect_terminology_patterns(entries)

        pattern_summary = ""
        if any(patterns.values()):
            pattern_parts = []
            if patterns["codes"]:
                pattern_parts.append(f"codes: {', '.join(patterns['codes'][:5])}")
            if patterns["abbreviations"]:
                pattern_parts.append(
                    f"abbreviations: {', '.join(patterns['abbreviations'][:5])}"
                )
            if patterns["date_formats"]:
                pattern_parts.append(
                    f"date formats: {', '.join(patterns['date_formats'][:5])}"
                )
            if patterns["identifiers"]:
                pattern_parts.append(
                    f"identifiers: {', '.join(patterns['identifiers'][:3])}"
                )
            if patterns["entities"]:
                pattern_parts.append(f"entities: {', '.join(patterns['entities'][:5])}")
            if patterns["data_types"]:
                pattern_parts.append(
                    f"data types: {', '.join(patterns['data_types'][:3])}"
                )
            pattern_summary = "\nDetected terminology patterns:\n  " + "\n  ".join(
                pattern_parts
            )

        parts.append(
            f"---\ndocument_id: {did}\n"
            f"file: {label}\n"
            f"Document metadata:\n{compact_meta(meta)}\n"
            f"Table of contents ({len(entries)} sections):\n"
            f"{compact_toc(did, entries)}{pattern_summary}\n"
        )
    return (
        f"{len(doc_ids)} document(s) in scope.\n\n"
        + "\n".join(parts)
        + f"\nRecent chat:\n{chat or '(none)'}\n\n"
        f"Current query: {state['query']}" + retry_hint
    )


async def fallback_heuristic(state: GraphState) -> RouterPlan:
    qnorm = state["query"].lower()
    qwords = {w for w in qnorm.replace("?", " ").split() if len(w) > 3}
    for did in scope_document_ids(state):
        entries = (await document_data.get_sections_index(did)) or []
        hits: list[str] = []
        for e in entries:
            nt = e.get("normalized_title") or normalize_title(e.get("title", ""))
            if not nt:
                continue
            if nt in qnorm or any(w == nt or w in nt for w in qwords):
                local = e.get("id")
                if local:
                    hits.append(f"{did}:{local}")
        if hits:
            return RouterPlan(
                route="structural",
                section_ids=hits[:4],
                rewritten_query=state["query"],
                query_variants=expand_query_variants(state["query"]),
                rationale="fallback: title keyword match",
            )
    return RouterPlan(
        route="semantic",
        rewritten_query=state["query"],
        query_variants=expand_query_variants(state["query"]),
        rationale="fallback: no title match",
    )


async def run(state: GraphState) -> dict[str, Any]:
    logger = JourneyLogger("router")
    logger.log_start("Query interpretation and retrieval planning")

    attempts = state.get("attempts", 0)
    avoid_route: str | None = None
    if attempts > 0:
        prev_route = (state.get("plan") or {}).get("route")
        avoid_route = prev_route
        logger.log_info(f"Retry attempt {attempts}, avoiding route: {avoid_route}")

    llm = get_llm(LLMConfig.ROUTER)
    structured = llm.with_structured_output(RouterPlan, method="json_mode")
    messages = [
        SystemMessage(content=get_router_prompt()),
        HumanMessage(content=await render_user(state, avoid_route=avoid_route)),
    ]

    plan = await fallback_heuristic(state)
    try:
        plan = await structured.ainvoke(messages)

        # Log key decisions
        logger.log_info(f"Intent: {plan.query_intent or 'not specified'}")
        if plan.key_entities:
            logger.log_info(f"Entities: {', '.join(plan.key_entities[:5])}")
        if plan.time_range_description:
            logger.log_info(f"Time range: {plan.time_range_description}")
        if plan.constraints_description:
            logger.log_info(f"Constraints: {plan.constraints_description}")
        logger.log_info(
            f"Route: {plan.route}, Variants: {len(plan.query_variants or [])}"
        )
    except Exception as e:
        logger.log_error("Structured output failed, using fallback", e)
        log.debug("router structured output failed; using fallback", exc_info=True)

    if avoid_route and plan.route == avoid_route:
        logger.log_info(f"Switching from {avoid_route} to hybrid")
        plan = plan.model_copy(update={"route": "hybrid"})

    if plan.route == "structural" and not plan.section_ids:
        logger.log_info("No section IDs, switching to semantic")
        plan = plan.model_copy(update={"route": "semantic"})

    # Supplement LLM-produced query variants with deterministic date
    # expansion — the LLM is the primary source, but deterministic
    # expansion catches format edge cases the LLM may miss.
    llm_variants = set(plan.query_variants or [])
    det_variants = set(expand_query_variants(plan.rewritten_query or state["query"]))
    all_variants = list(llm_variants | det_variants)
    if len(all_variants) > len(plan.query_variants or []):
        logger.log_debug(
            f"Expanded variants: {len(plan.query_variants or [])} → {len(all_variants)}"
        )
        plan = plan.model_copy(update={"query_variants": all_variants})

    journey_data = logger.log_complete(
        {
            "route": plan.route,
            "intent": plan.query_intent,
            "entities": plan.key_entities,
            "time_range": plan.time_range_description,
            "constraints": plan.constraints_description,
            "variants_count": len(plan.query_variants or []),
        }
    )

    step = {
        "node": "router",
        "duration_ms": journey_data["duration_ms"],
        "output": plan.model_dump(),
    }
    return {"plan": plan.model_dump(), "trace": [step], "journey": [journey_data]}
