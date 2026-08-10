from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.processing.concurrency import table_semaphore
from app.processing.structure import ElementRef, Section
from app.settings import settings

log = logging.getLogger(__name__)

DESCRIBE_PROMPT = (
    "You are writing a search-index entry for a table. Your output will be "
    "embedded as a vector and matched against user queries. Be specific and "
    "keyword-rich — every noun you include is a retrieval hook.\n\n"
    "Given the table markdown below (header + first and last few rows), "
    "write a 4-6 sentence description that includes:\n"
    "1. Table name/title if visible\n"
    "2. EVERY column name, in order\n"
    "3. Row scope: total rows, what kinds of entities (countries, products, "
    "years, etc.), any groupings (by region, category, etc.)\n"
    "4. Page range (if given)\n"
    "5. 5-8 notable/sample entities with their values (pick largest, smallest, "
    "most interesting) — these anchor entity-name queries\n"
    "6. Any obvious comparisons or trends a user might ask about\n\n"
    "Example output:\n"
    '"Table 1.A: Population by Country, 1950-2010 (pp.1-6, 241 rows). '
    "Columns: Country, 1950 Population (Women, Men), 1980 Population (Women, "
    "Men), 2010 Population (Women, Men), Sex ratio (women per 100 men, 2010), "
    "% population over 60 (Women, Men), Total fertility rate (1950-55, 1980-85, "
    "2005-10), Singulate mean age at marriage (Year, Women, Men). Covers 241 "
    "countries across 5 regions: Africa, Asia, Latin America & Caribbean, "
    "Oceania, More developed regions. Notable: China highest 2010 population "
    "(1.34B), India second (1.22B), Vatican City smallest (~800). Nigeria "
    'highest fertility rate (7.2), Japan oldest mean marriage age (29.0)."\n\n'
    "Table markdown:\n{markdown}\n"
)

TABLE_DESCRIBE_PREVIEW_ROWS = 5  # first + last N rows sent to the describer


@dataclass
class TableDiagnostics:
    """Observability for one table-extraction pass."""

    total_pages: int = 0
    pages_detected: list[int] = field(default_factory=list)
    pages_skipped: list[int] = field(default_factory=list)
    lattice_pages: list[int] = field(default_factory=list)
    stream_pages: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    tables_extracted: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_pages": self.total_pages,
            "pages_detected": self.pages_detected,
            "pages_skipped": self.pages_skipped,
            "lattice_pages": self.lattice_pages,
            "stream_pages": self.stream_pages,
            "errors": self.errors,
            "tables_extracted": self.tables_extracted,
        }


def _build_describe_snippet(markdown: str, page_range: list[int] | None = None) -> str:
    """Build a compact markdown preview for the table description LLM.

    Includes the header row, the first *preview_rows* data rows, a ``...``
    marker, and the last *preview_rows* data rows.  A page-range line is
    prepended when available so the describer can include it.
    """
    lines = markdown.strip().splitlines()
    n = TABLE_DESCRIBE_PREVIEW_ROWS
    header = [f"<!-- total rows incl. header+sep: {len(lines)} -->"]
    if page_range and len(page_range) == 2:
        header.append(
            f"<!-- pages {page_range[0]}-{page_range[1]} -->"
            if page_range[1] > page_range[0]
            else f"<!-- page {page_range[0]} -->"
        )
    header.append("")

    if len(lines) <= 2 + 2 * n:
        # Small enough — send everything
        return "\n".join(header) + markdown

    head = lines[: 2 + n]  # header + sep + first N data rows
    tail = lines[-n:]  # last N data rows
    return "\n".join(header) + "\n".join(head) + "\n...\n" + "\n".join(tail)


def _collapse_headers(lines: list[str]) -> list[str]:
    """Collapse multi-row markdown headers into a single clean row.

    camelot's stream flavour often emits several partial header rows
    (merged cells become empty strings) scattered above *and* below the
    first separator.  This function collects every header fragment,
    concatenates non-empty cell values per column, and replaces the whole
    header block with one clean row + one separator.
    """
    pipe_lines = [line for line in lines if line.startswith("|")]
    if len(pipe_lines) < 2:
        return lines

    # Locate the first separator row
    sep_idx: int | None = None
    for i, line in enumerate(lines):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if cells and all(
            c.replace("-", "").replace(":", "").strip() == "" for c in cells
        ):
            sep_idx = i
            break
    if sep_idx is None:
        return lines

    # Determine column count from the separator
    sep_cells = [c.strip() for c in lines[sep_idx].split("|")[1:-1]]
    ncols = len(sep_cells)

    # Collect header rows: everything before the separator …
    header_rows: list[list[str]] = []
    for i in range(sep_idx):
        if lines[i].startswith("|"):
            header_rows.append([c.strip() for c in lines[i].split("|")[1:-1]])

    # … and header-continuation rows after the separator, up to (but not
    # including) the first *data* row.  Data cells look like "4 288"
    # (thousand-separated), "7.3" (decimal), or ".." (placeholder).
    # Header cells may contain years ("1950") or ranges ("1950–") but
    # never more than 1-2 per row.
    import re

    _data_cell = re.compile(r"^\s*(?:\d{1,3}(?:\s\d{3})+|\d+\.\d+|[.]{2,})\s*$")
    first_data: int = sep_idx + 1
    for i in range(sep_idx + 1, len(lines)):
        if not lines[i].startswith("|"):
            continue
        cells = [c.strip() for c in lines[i].split("|")[1:-1]]
        data_count = sum(1 for c in cells if _data_cell.match(c))
        # Data rows have many data cells; header fragments at most 1-2
        if data_count >= 3:
            first_data = i
            break
        header_rows.append(cells)
        first_data = i + 1

    if len(header_rows) <= 1:
        return lines

    # Collapse: per column, concatenate non-empty values top→bottom
    collapsed: list[str] = []
    for col in range(ncols):
        parts: list[str] = []
        for row in header_rows:
            if col < len(row) and row[col]:
                parts.append(row[col])
        collapsed.append(" ".join(parts) if parts else "")

    # Rebuild: collapsed header + one separator + data rows
    out = [
        "| " + " | ".join(collapsed) + " |",
        lines[sep_idx],  # keep original separator
    ]
    out.extend(lines[first_data:])
    return out


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
    # Collapse multi-row headers from merged cells into clean labels
    out = _collapse_headers(out)
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


_OVERLAP_SUPPRESS_THRESHOLD = 0.5


def _suppress_text_in_table_bboxes(root: Section) -> int:
    """Remove text elements whose bbox substantially overlaps a table element.

    Table extraction (camelot) and text extraction (unstructured) both pick up
    the same content, producing duplicate noisy text chunks.  This function
    walks *root* and prunes text-type ``ElementRef`` entries that fall inside
    a detected table's bounding box on the same page.

    Returns the number of text elements removed.
    """
    # Collect table bboxes by page
    table_bboxes: dict[int, list[list[float]]] = {}
    for el in root.elements:
        if el.type == "table" and el.bbox:
            table_bboxes.setdefault(el.page, []).append(el.bbox)
    # Also walk child sections
    stack: list[Section] = [root]
    while stack:
        sec = stack.pop()
        for el in sec.elements:
            if el.type == "table" and el.bbox:
                table_bboxes.setdefault(el.page, []).append(el.bbox)
        stack.extend(sec.children)

    if not table_bboxes:
        return 0

    removed = 0
    stack = [root]
    while stack:
        sec = stack.pop()
        kept: list[ElementRef] = []
        for el in sec.elements:
            if el.type == "text" and el.bbox and el.page in table_bboxes:
                drop = any(
                    bbox_overlap(el.bbox, tb) >= _OVERLAP_SUPPRESS_THRESHOLD
                    for tb in table_bboxes[el.page]
                )
                if drop:
                    removed += 1
                    continue
            kept.append(el)
        sec.elements[:] = kept
        stack.extend(sec.children)

    return removed


def append_markdown_rows(base_md: str, next_md: str) -> str:
    """Append data rows from *next_md* onto *base_md*, skipping its header+sep.

    Both markdown strings must be GFM pipe tables with the same column count.
    """
    base_lines = base_md.strip().splitlines()
    next_lines = next_md.strip().splitlines()
    # next_md[2:] skips header and separator rows; preserves data rows only
    return "\n".join(base_lines + next_lines[2:])


_MERGE_MAX_PAGE_GAP = 2
_MERGE_COL_TOLERANCE = 2
_MERGE_HEADER_SIMILARITY_MIN = 0.3


def _header_tokens(markdown: str) -> set[str]:
    """Return lowercased, normalised tokens from the first row of *markdown*."""
    lines = markdown.strip().splitlines()
    for line in lines:
        if line.startswith("|") and not all(
            c.strip() in ("", "---", "---:", ":---", ":---:")
            for c in line.split("|")[1:-1]
        ):
            cells = [c.strip().lower() for c in line.split("|")[1:-1]]
            tokens: set[str] = set()
            for cell in cells:
                for token in cell.split():
                    t = token.strip(".,;:()[]{}%$")
                    if t:
                        tokens.add(t)
            return tokens
    return set()


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _same_table_structure(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return True when *b* looks like a continuation of table *a*.

    Checks column-count proximity, page adjacency, and header-row token
    similarity.  Tables that share the same columns and have recognisably
    similar headers are safe to merge; unrelated tables on adjacent pages
    with coincidentally similar column counts are not.
    """
    _, ca = count_table_rows(a["markdown"])
    _, cb = count_table_rows(b["markdown"])
    if abs(ca - cb) > _MERGE_COL_TOLERANCE:
        return False

    gap = abs(b["page"] - a.get("page_range", [a["page"]])[-1])
    if gap > _MERGE_MAX_PAGE_GAP:
        return False

    # Header similarity — unrelated tables may have the same column count
    # but different headers (e.g. two 5-column tables on adjacent pages).
    tok_a = _header_tokens(a["markdown"])
    tok_b = _header_tokens(b["markdown"])
    if tok_a and tok_b:
        sim = _jaccard(tok_a, tok_b)
        if sim < _MERGE_HEADER_SIMILARITY_MIN:
            return False

    return True


def _merge_consecutive(
    tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge consecutive tables that share the same column structure.

    The first table's header row serves as the canonical header; subsequent
    data rows are appended.  Each merged entry gains a ``page_range`` field.
    """
    if len(tables) <= 1:
        for t in tables:
            t.setdefault("page_range", [t["page"], t["page"]])
        return tables

    tables = sorted(tables, key=lambda t: (t["page"], t.get("bbox", [0])[0] or 0))
    merged: list[dict[str, Any]] = []

    for t in tables:
        if merged and _same_table_structure(merged[-1], t):
            prev = merged[-1]
            prev["page_range"][1] = t["page"]
            prev["markdown"] = append_markdown_rows(prev["markdown"], t["markdown"])
            # Favour stream flavour when available
            if t["flavor"] == "stream":
                prev["flavor"] = "stream"
        else:
            t.setdefault("page_range", [t["page"], t["page"]])
            merged.append(t)

    return merged


def detect_table_pages(pdf_file: Path) -> tuple[list[int], TableDiagnostics]:
    """Heuristically find pages that are likely to contain tables.

    Uses cheap pypdf text extraction (no rendering, no Camelot) to look for
    tabular structure: pipe-separated rows, repeated tab runs, or numeric
    multi-column lines.  Pages without any signal are skipped by Camelot,
    which avoids the expensive two-pass extraction on clearly non-table
    documents.
    """
    import pypdf

    diagnostics = TableDiagnostics()
    detected: list[int] = []
    try:
        reader = pypdf.PdfReader(str(pdf_file), strict=False)
        diagnostics.total_pages = len(reader.pages)
        for page_no, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if not lines:
                continue
            pipe_lines = sum(
                1
                for ln in lines
                if "|" in ln and len(ln) >= settings.table_page_line_min_len
            )
            numeric_lines = 0
            tab_lines = 0
            for ln in lines:
                if "\t" in ln:
                    tab_lines += 1
                elif len(ln) >= settings.table_page_line_min_len:
                    cells = [c for c in ln.split("  ") if c.strip()]
                    numeric = sum(1 for c in cells if any(ch.isdigit() for ch in c))
                    if len(cells) >= 3 and numeric >= 2:
                        numeric_lines += 1
            if (
                pipe_lines >= settings.table_page_pipe_min_lines
                or tab_lines >= settings.table_page_pipe_min_lines
                or numeric_lines >= settings.table_page_numeric_min_lines
            ):
                detected.append(page_no)
        diagnostics.pages_detected = list(detected)
        diagnostics.pages_skipped = [
            p for p in range(1, diagnostics.total_pages + 1) if p not in detected
        ]
    except Exception as exc:
        diagnostics.errors.append(f"table-page detection failed: {exc}")
        log.warning("table-page detection failed for %s: %s", pdf_file, exc)
    return detected, diagnostics


def extract_tables(
    pdf_file: Path,
    diagnostics: TableDiagnostics | None = None,
) -> list[dict[str, Any]]:
    import camelot

    diag = diagnostics or TableDiagnostics()
    results: list[dict[str, Any]] = []
    lattice_by_page: dict[int, list[dict[str, Any]]] = {}

    detected_pages, detected_diag = detect_table_pages(pdf_file)
    diag.pages_detected = list(detected_pages)
    diag.total_pages = detected_diag.total_pages
    diag.pages_skipped = [
        p for p in range(1, diag.total_pages + 1) if p not in detected_pages
    ]

    # No table-like pages found: skip Camelot entirely and fall back to the
    # unstructured HTML placeholders already attached to table elements.
    if not detected_pages:
        log.info(
            "table detection: no table-like pages in %s; skipping Camelot",
            pdf_file,
        )
        return results

    try:
        lattice = camelot.read_pdf(
            str(pdf_file),
            pages=",".join(str(p) for p in sorted(detected_pages)),
            flavor="lattice",
        )
        diag.lattice_pages = sorted({int(t.page) for t in lattice})
    except Exception as exc:
        diag.errors.append(f"lattice extraction failed: {exc}")
        log.warning("camelot lattice failed for %s: %s", pdf_file, exc)
        lattice = []

    for tbl in lattice or []:
        page = int(tbl.page)
        md = df_to_markdown(tbl.df)
        if not md:
            continue
        entry = {
            "page": page,
            "markdown": md,
            "bbox": camelot_bbox(tbl),
            "flavor": "lattice",
        }
        results.append(entry)
        lattice_by_page.setdefault(page, []).append(entry)

    # Run stream on pages where lattice missed OR produced only 1-col tables
    pages_need_stream: set[int] = set()
    for p in detected_pages:
        if p not in lattice_by_page:
            pages_need_stream.add(p)
        else:
            # Lattice with only 1 column → likely a merged-cell table;
            # stream flavour often recovers proper column structure.
            if all(count_table_rows(e["markdown"])[1] <= 1 for e in lattice_by_page[p]):
                pages_need_stream.add(p)

    if pages_need_stream:
        try:
            stream = camelot.read_pdf(
                str(pdf_file),
                pages=",".join(str(p) for p in sorted(pages_need_stream)),
                flavor="stream",
            )
            diag.stream_pages = sorted({int(t.page) for t in stream})
        except Exception as exc:
            diag.errors.append(f"stream extraction failed: {exc}")
            log.warning("camelot stream failed for %s: %s", pdf_file, exc)
            stream = []
        stream_cols_by_page: dict[int, int] = {}
        for tbl in stream or []:
            md = df_to_markdown(tbl.df)
            if not md:
                continue
            page = int(tbl.page)
            _, ncols = count_table_rows(md)
            results.append(
                {
                    "page": page,
                    "markdown": md,
                    "bbox": camelot_bbox(tbl),
                    "flavor": "stream",
                }
            )
            stream_cols_by_page[page] = max(stream_cols_by_page.get(page, 0), ncols)

        # Drop lattice results from pages where stream found better structure
        pages_with_good_stream = {p for p, c in stream_cols_by_page.items() if c > 1}
        if pages_with_good_stream:
            results = [
                r
                for r in results
                if not (
                    r["flavor"] == "lattice" and r["page"] in pages_with_good_stream
                )
            ]

    # Merge consecutive pages that share the same table structure ----------
    results = _merge_consecutive(results)
    diag.tables_extracted = len(results)

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


async def describe_one(
    markdown: str,
    page_range: list[int] | None = None,
) -> str:
    """Generate a keyword-rich description of *markdown* via OpenRouter.

    Uses the OpenAI SDK so that provider-specific parameters (reasoning)
    travel through ``extra_body``.
    """
    from openai import AsyncOpenAI

    if not settings.openrouter_api_key:
        return ""

    snippet = _build_describe_snippet(markdown, page_range)
    max_retries = max(0, settings.table_describer_max_retries)
    for attempt in range(max_retries + 1):
        client = AsyncOpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            default_headers={
                "HTTP-Referer": "https://localhost/chat-pdf",
                "X-Title": "chat_pdf table description",
            },
            timeout=settings.slow_upstream_request_timeout,
        )
        try:
            response = await client.chat.completions.create(
                model=settings.table_describer_model,
                messages=[
                    {
                        "role": "user",
                        "content": DESCRIBE_PROMPT.format(markdown=snippet[:6000]),
                    }
                ],
                extra_body={"reasoning": {"effort": "minimal"}},
            )
            description = str(response.choices[0].message.content or "").strip()
            if description:
                return description
            log.warning(
                "table describe_one returned empty content (attempt %d)", attempt
            )
        except Exception:
            log.warning(
                "table describe_one failed (model=%s, timeout=%.0fs, attempt=%d/%d)",
                settings.table_describer_model,
                settings.slow_upstream_request_timeout,
                attempt + 1,
                max_retries + 1,
                exc_info=True,
            )
        if attempt < max_retries:
            delay = settings.table_describer_retry_base_seconds * (2**attempt)
            await asyncio.sleep(delay * (0.5 + random.random()))
    return ""


def count_table_rows(markdown: str) -> tuple[int, int]:
    """Return (data_rows, columns) from a GFM pipe-table markdown string.

    A valid pipe table has at least a header row and a delimiter row.
    Data rows are everything below the delimiter.
    """
    lines = [line for line in markdown.strip().splitlines() if line.startswith("|")]
    if len(lines) < 2:
        return 0, 0
    cols = lines[0].count("|") - 1
    data_rows = len(lines) - 2  # header + separator
    return max(0, data_rows), max(1, cols)


async def enrich_tables(
    pdf_file: Path,
    root: Section,
    placeholders: list[ElementRef],
) -> TableDiagnostics:
    """Extract tables with camelot and attach them to the section tree.

    Existing ``ElementRef`` table placeholders (from the unstructured partition)
    are matched to camelot tables by bbox overlap where possible.  Any camelot
    tables that do *not* match an existing placeholder are injected as synthetic
    ``ElementRef`` entries attached to *root* so they still reach the chunker.
    """
    table_placeholders = [e for e in placeholders if e.type == "table"]
    diagnostics = TableDiagnostics()

    camelot_tables = await asyncio.to_thread(extract_tables, pdf_file, diagnostics)
    if not camelot_tables:
        diagnostics.errors.append(
            "no tables extracted; using unstructured table HTML placeholders"
        )
        return diagnostics

    # Initialise existing placeholders ----------------------------------------
    for ph in table_placeholders:
        ph.extra.setdefault("markdown", "")
        ph.extra.setdefault("description", "")

    mapping = match_to_placeholder(camelot_tables, table_placeholders)

    # Collect all table refs to describe (existing + synthetic) ----------------
    to_describe: list[tuple[ElementRef, str, list[int] | None]] = []

    # 1. Existing placeholders that matched a camelot table
    for ph in table_placeholders:
        ct = mapping.get(ph.id)
        if ct:
            pr = ct.get("page_range", [ct["page"], ct["page"]])
            ph.extra["markdown"] = ct["markdown"]
            ph.extra["camelot_flavor"] = ct["flavor"]
            ph.extra["page_range"] = pr
            to_describe.append((ph, ct["markdown"], pr))

    # 2. Camelot tables that didn't match any placeholder → synthetic entries
    used_camelot_indices: set[int] = set()
    for ct in mapping.values():
        for idx, ct2 in enumerate(camelot_tables):
            if ct2 is ct:
                used_camelot_indices.add(idx)
                break

    el_counter = len(placeholders)
    for idx, ct in enumerate(camelot_tables):
        if idx in used_camelot_indices:
            continue
        el_counter += 1
        pr = ct.get("page_range", [ct["page"], ct["page"]])
        synthetic = ElementRef(
            id=f"el-{el_counter}",
            type="table",
            page=ct["page"],
            text="",
            bbox=ct.get("bbox"),
            extra={
                "markdown": ct["markdown"],
                "camelot_flavor": ct["flavor"],
                "description": "",
                "page_range": pr,
            },
        )
        root.elements.append(synthetic)
        to_describe.append((synthetic, ct["markdown"], pr))

    # 3. Generate descriptions for everything ----------------------------------
    if not to_describe:
        return diagnostics

    async with table_semaphore():
        descriptions = await asyncio.gather(
            *[describe_one(md, page_range=pr) for _, md, pr in to_describe]
        )
    succeeded = 0
    for (ph, _, _), desc in zip(to_describe, descriptions, strict=False):
        ph.extra["description"] = desc
        if desc:
            succeeded += 1
    if succeeded < len(to_describe):
        log.warning(
            "table description: %d/%d succeeded (model=%s)",
            succeeded,
            len(to_describe),
            settings.table_describer_model,
        )
        diagnostics.errors.append(
            f"table descriptions: {len(to_describe) - succeeded}/"
            f"{len(to_describe)} failed; heuristic fallback used"
        )

    # 4. Prune text elements that overlap detected table regions ---------------
    removed = _suppress_text_in_table_bboxes(root)
    if removed:
        log.debug("suppressed %d text element(s) inside table bboxes", removed)

    return diagnostics
