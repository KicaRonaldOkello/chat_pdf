"""Date alias expansion for query variants."""

from __future__ import annotations

import re

_MONTH_NAMES = {
    "january": "Jan", "february": "Feb", "march": "Mar", "april": "Apr",
    "may": "May", "june": "Jun", "july": "Jul", "august": "Aug",
    "september": "Sep", "october": "Oct", "november": "Nov", "december": "Dec",
}


def expand_date_variants(date_str: str) -> list[str]:
    variants = [date_str]

    month_year_match = re.search(r"(\w+)\s+(\d{4})", date_str)
    if month_year_match:
        month, year = month_year_match.groups()
        month_lower = month.lower()
        if month_lower in _MONTH_NAMES:
            short_month = _MONTH_NAMES[month_lower]
            short_year = year[-2:]
            variants.extend([
                f"{short_month}-{short_year}",
                f"{short_month} {year}",
                f"{list(_MONTH_NAMES).index(month_lower) + 1:02d}/{year}",
                f"{list(_MONTH_NAMES).index(month_lower) + 1:02d}-{short_year}",
            ])

    abbrev_match = re.search(r"([A-Z][a-z]{2})-(\d{2})", date_str)
    if abbrev_match:
        short_month, short_year = abbrev_match.groups()
        for full, abbrev in _MONTH_NAMES.items():
            if abbrev == short_month:
                full_year = f"20{short_year}"
                month_num = list(_MONTH_NAMES).index(full) + 1
                variants.extend([
                    f"{full} {full_year}",
                    f"{abbrev} {full_year}",
                    f"{month_num:02d}/{full_year}",
                ])
                break

    slash_match = re.search(r"(\d{1,2})/(\d{4})", date_str)
    if slash_match:
        month_num_str, year = slash_match.groups()
        month_num = int(month_num_str)
        if 1 <= month_num <= 12:
            full_month = list(_MONTH_NAMES)[month_num - 1]
            short_month = _MONTH_NAMES[full_month]
            short_year = year[-2:]
            variants.extend([
                f"{full_month} {year}",
                f"{short_month}-{short_year}",
                f"{short_month} {year}",
            ])

    return list(dict.fromkeys(variants))


def extract_dates_from_query(query: str) -> list[str]:
    dates: list[str] = []
    dates.extend(re.findall(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?"
        r"|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?"
        r"|Dec(?:ember)?)\s+\d{4}\b", query, re.IGNORECASE,
    ))
    dates.extend(re.findall(r"\b[A-Z][a-z]{2}-\d{2}\b", query))
    dates.extend(re.findall(r"\b\d{1,2}/\d{4}\b", query))
    return dates


def expand_query_variants(query: str) -> list[str]:
    variants = [query]
    for date in extract_dates_from_query(query):
        for variant in expand_date_variants(date):
            if variant != date:
                expanded = query.replace(date, variant)
                if expanded not in variants:
                    variants.append(expanded)
    return variants
