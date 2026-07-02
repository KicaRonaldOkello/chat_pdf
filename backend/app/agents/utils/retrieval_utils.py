"""Deterministic chunk filters for the retrieval judge."""

from __future__ import annotations

import re
from typing import Any

_MONTH_TO_NUM = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may_short": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DATE_PATTERNS = [
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
    r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?"
    r"|Dec(?:ember)?)\s+\d{4}\b",
    r"\b[A-Z][a-z]{2}-\d{2}\b",
    r"\b\d{4}-\d{1,2}-\d{1,2}\b",
    r"\b\d{1,2}/\d{4}\b",
]


def _parse_date_string(date_str: str) -> tuple[int, int, int] | None:
    date_str = date_str.strip()

    match = re.search(r"(\w+)\s+(\d{4})", date_str, re.IGNORECASE)
    if match:
        month_name, year = match.groups()
        month_val = _MONTH_TO_NUM.get(month_name.lower())
        if month_val is not None:
            return (int(year), month_val, 1)

    match = re.search(r"([A-Z][a-z]{2})-(\d{2})", date_str)
    if match:
        month_abbr, short_year = match.groups()
        month_val2 = _MONTH_TO_NUM.get(month_abbr.lower())
        if month_val2 is not None:
            return (2000 + int(short_year), month_val2, 1)

    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", date_str)
    if match:
        year, month, day = match.groups()
        return (int(year), int(month), int(day))

    match = re.search(r"(\d{1,2})/(\d{4})", date_str)
    if match:
        month, year = match.groups()
        return (int(year), int(month), 1)

    return None


def _extract_dates_from_text(text: str) -> list[tuple[int, int, int]]:
    dates: list[tuple[int, int, int]] = []
    for pattern in _DATE_PATTERNS:
        for match in re.findall(pattern, text, re.IGNORECASE):
            match_str = " ".join(match) if isinstance(match, tuple) else match
            parsed = _parse_date_string(match_str)
            if parsed:
                dates.append(parsed)
    return dates


def filter_chunks_by_time_range(
    hits: list[dict[str, Any]],
    time_range_start: str,
    time_range_end: str,
) -> list[dict[str, Any]]:
    if not time_range_start and not time_range_end:
        return hits

    start_date = _parse_date_string(time_range_start) if time_range_start else None
    end_date = _parse_date_string(time_range_end) if time_range_end else None
    if not start_date and not end_date:
        return hits

    filtered: list[dict[str, Any]] = []
    for hit in hits:
        text = hit.get("display_text", "") + " " + hit.get("text_for_embedding", "")
        chunk_dates = _extract_dates_from_text(text)
        if not chunk_dates:
            filtered.append(hit)
            continue

        in_range = False
        for chunk_date in chunk_dates:
            if start_date and end_date:
                if start_date <= chunk_date <= end_date:
                    in_range = True
                    break
            elif (start_date and chunk_date >= start_date) or (end_date and chunk_date <= end_date):
                in_range = True
                break

        if in_range:
            filtered.append(hit)

    return filtered if filtered else hits


def filter_chunks_by_entities(
    hits: list[dict[str, Any]],
    key_entities: list[str],
) -> list[dict[str, Any]]:
    if not key_entities:
        return hits

    filtered: list[dict[str, Any]] = []
    for hit in hits:
        text = (
            hit.get("display_text", "") + " "
            + hit.get("text_for_embedding", "") + " "
            + " ".join(hit.get("keywords", []))
        ).lower()
        if any(entity.lower() in text for entity in key_entities):
            filtered.append(hit)

    return filtered if filtered else hits


def filter_chunks_by_sections(
    hits: list[dict[str, Any]],
    target_sections: list[str],
) -> list[dict[str, Any]]:
    if not target_sections:
        return hits

    filtered: list[dict[str, Any]] = []
    for hit in hits:
        section_id = hit.get("id", "")
        section_path = hit.get("section_path", "")
        if any(
            target in section_id or target in section_path
            for target in target_sections
        ):
            filtered.append(hit)

    return filtered if filtered else hits
