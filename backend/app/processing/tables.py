from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx

from app.config import (
    OLLAMA_OPENAI_API_KEY,
    OLLAMA_OPENAI_BASE_URL,
    SLOW_UPSTREAM_REQUEST_TIMEOUT,
    TABLE_DESCRIBER_MODEL,
)
from app.processing.structure import ElementRef

DESCRIBE_PROMPT = (
    "You are summarising a table for a retrieval index.\n"
    "Write 2-4 sentences describing WHAT this table shows, its columns, its "
    "row groupings, and the most notable values or comparisons a reader "
    "would ask about. Do NOT restate the entire table.\n\n"
    "Table (markdown):\n{markdown}\n"
)


def df_to_markdown(df: Any) -> str:
    try:
        rows = df.values.tolist()
    except Exception:
        return ""
    if not rows:
        return ""
    header = [str(x) for x in rows[0]]
    body = rows[1:] if len(rows) > 1 else []
    out = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join(["---"] * len(header)) + "|",
    ]
    for r in body:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def camelot_bbox(tbl: Any) -> list[float] | None:
    bbox = getattr(tbl, "_bbox", None)
    if bbox and len(bbox) == 4:
        return [float(v) for v in bbox]
    return None


def bbox_overlap(a: list[float], b: list[float]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    iw = max(0.0, ix1 - ix0)
    ih = max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1e-6, (ax1 - ax0) * (ay1 - ay0))
    return inter / area_a


def extract_tables(pdf_file: Path) -> list[dict[str, Any]]:
    import camelot

    results: list[dict[str, Any]] = []
    pages_with_lattice: set[int] = set()

    try:
        lattice = camelot.read_pdf(str(pdf_file), pages="all", flavor="lattice")
    except Exception:
        lattice = []

    for tbl in lattice or []:
        page = int(tbl.page)
        pages_with_lattice.add(page)
        md = df_to_markdown(tbl.df)
        if not md:
            continue
        results.append(
            {
                "page": page,
                "markdown": md,
                "bbox": camelot_bbox(tbl),
                "flavor": "lattice",
            }
        )

    try:
        import pypdf

        num_pages = len(pypdf.PdfReader(str(pdf_file)).pages)
    except Exception:
        num_pages = 0

    missing = [p for p in range(1, num_pages + 1) if p not in pages_with_lattice]
    if missing:
        try:
            stream = camelot.read_pdf(
                str(pdf_file),
                pages=",".join(str(p) for p in missing),
                flavor="stream",
            )
        except Exception:
            stream = []
        for tbl in stream or []:
            md = df_to_markdown(tbl.df)
            if not md:
                continue
            results.append(
                {
                    "page": int(tbl.page),
                    "markdown": md,
                    "bbox": camelot_bbox(tbl),
                    "flavor": "stream",
                }
            )

    return results


def match_to_placeholder(
    camelot_tables: list[dict[str, Any]],
    placeholders: list[ElementRef],
) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    used: set[int] = set()

    by_page: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    for idx, ct in enumerate(camelot_tables):
        by_page.setdefault(ct["page"], []).append((idx, ct))

    for ph in placeholders:
        candidates = by_page.get(ph.page, [])
        if not candidates:
            continue
        best_idx = -1
        best_score = 0.0
        for idx, ct in candidates:
            if idx in used:
                continue
            if ph.bbox and ct.get("bbox"):
                score = bbox_overlap(ph.bbox, ct["bbox"])
            else:
                score = 0.0
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx == -1:
            for idx, _ct in candidates:
                if idx not in used:
                    best_idx = idx
                    break
        if best_idx == -1:
            continue
        used.add(best_idx)
        mapping[ph.id] = camelot_tables[best_idx]

    return mapping


async def describe_one(client: httpx.AsyncClient, markdown: str) -> str:
    payload = {
        "model": TABLE_DESCRIBER_MODEL,
        "messages": [
            {
                "role": "user",
                "content": DESCRIBE_PROMPT.format(markdown=markdown[:6000]),
            }
        ],
        "stream": False,
    }
    try:
        r = await client.post(
            f"{OLLAMA_OPENAI_BASE_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {OLLAMA_OPENAI_API_KEY}"},
            timeout=SLOW_UPSTREAM_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return str(data["choices"][0]["message"]["content"]).strip()
    except Exception:
        return ""


async def enrich_tables(
    pdf_file: Path,
    placeholders: list[ElementRef],
) -> None:
    table_placeholders = [e for e in placeholders if e.type == "table"]
    if not table_placeholders:
        return

    camelot_tables = await asyncio.to_thread(extract_tables, pdf_file)

    for ph in table_placeholders:
        ph.extra.setdefault("markdown", "")
        ph.extra.setdefault("description", "")

    mapping = match_to_placeholder(camelot_tables, table_placeholders)

    to_describe: list[tuple[ElementRef, str]] = []
    for ph in table_placeholders:
        ct = mapping.get(ph.id)
        if ct:
            ph.extra["markdown"] = ct["markdown"]
            ph.extra["camelot_flavor"] = ct["flavor"]
            to_describe.append((ph, ct["markdown"]))

    if not to_describe:
        return

    async with httpx.AsyncClient() as client:
        descriptions = await asyncio.gather(
            *[describe_one(client, md) for _, md in to_describe]
        )
    for (ph, _), desc in zip(to_describe, descriptions, strict=False):
        ph.extra["description"] = desc
