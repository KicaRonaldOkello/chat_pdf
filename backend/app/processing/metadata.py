from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
import tiktoken

from app.clients import openrouter_json
from app.processing.structure import Section
from app.processing.tree import walk_sections
from app.settings import settings

TOKEN_ENC = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(TOKEN_ENC.encode(text, disallowed_special=()))


def truncate_to_max_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    ids = TOKEN_ENC.encode(text, disallowed_special=())
    if len(ids) <= max_tokens:
        return text
    return TOKEN_ENC.decode(ids[:max_tokens])


def section_body_text_limited_by_tokens(section: Section, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    raw = section_body_text(section, limit_chars=1000000)
    return truncate_to_max_tokens(raw, max_tokens)


log = logging.getLogger(__name__)


NUMBER_PREFIX_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*|[IVX]+|\([a-z]\)|[A-Z]\.)\s+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-']+")
STOP = {
    "the",
    "a",
    "an",
    "of",
    "and",
    "or",
    "to",
    "in",
    "for",
    "on",
    "with",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "our",
    "we",
    "they",
    "their",
    "by",
    "as",
    "at",
    "from",
    "which",
    "used",
    "use",
    "using",
}


def normalize_title(title: str) -> str:
    """Lower-case, strip leading section numbering.  Used for router matching."""
    t = NUMBER_PREFIX_RE.sub("", title or "").strip()
    return t.lower()


def section_body_text(section: Section, limit_chars: int = 4000) -> str:
    parts: list[str] = []
    total = 0
    for el in section.elements:
        if el.type not in ("text", "formula"):
            continue
        text = (el.text or "").strip()
        if not text:
            continue
        parts.append(text)
        total += len(text)
        if total >= limit_chars:
            break
    return "\n\n".join(parts)[:limit_chars]


def heuristic_keywords(text: str, k: int = 8) -> list[str]:
    counts: dict[str, int] = {}
    for m in WORD_RE.finditer(text.lower()):
        w = m.group(0)
        if len(w) < 4 or w in STOP:
            continue
        counts[w] = counts.get(w, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [w for w, _ in ranked[:k]]


def heuristic_summary(text: str, max_sentences: int = 2, max_chars: int = 280) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    summary = " ".join(sentences[:max_sentences])
    return summary[:max_chars]


def element_counts(section: Section) -> dict[str, int]:
    c: dict[str, int] = {}
    for el in section.elements:
        c[el.type] = c.get(el.type, 0) + 1
    return c


JSON_CODEBLOCK_RE = re.compile(
    r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE
)


def extract_json(raw: str) -> Any:
    text = JSON_CODEBLOCK_RE.sub("", raw.strip()).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                continue
    return json.loads(text)


async def ollama_json_chat(
    client: httpx.AsyncClient,
    *,
    model: str,
    system: str,
    user: str,
    timeout: float = 60.0,
    max_output_tokens: int | None = None,
) -> Any | None:
    options: dict[str, Any] = {"temperature": settings.metadata_llm_temperature}
    if max_output_tokens is not None:
        options["num_predict"] = int(max_output_tokens)

    content = ""
    try:
        r = await client.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "format": "json",
                "stream": False,
                "options": options,
            },
            timeout=timeout,
        )
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "")
        return extract_json(content)
    except json.JSONDecodeError as e:
        preview = content.strip().replace("\n", " ")[:200]
        log.warning(
            "ollama json chat parse failed (model=%s, bytes=%d): %s | preview: %s",
            model,
            len(content),
            e,
            preview,
        )
        return None
    except httpx.HTTPStatusError as e:
        body = (e.response.text or "")[:800]
        log.warning(
            "ollama json chat HTTP %s (model=%s, url=%s): %s | body: %s",
            e.response.status_code,
            model,
            f"{settings.ollama_base_url}/api/chat",
            e,
            body,
        )
        return None
    except httpx.TimeoutException as e:
        log.warning(
            "ollama json chat timeout (model=%s timeout_s=%s): %s %r",
            model,
            timeout,
            type(e).__name__,
            e,
        )
        return None
    except httpx.RequestError as e:
        log.warning(
            "ollama json chat request failed (model=%s): %s %r url=%s",
            model,
            type(e).__name__,
            e,
            f"{settings.ollama_base_url}/api/chat",
        )
        return None
    except Exception as e:
        log.warning(
            "ollama json chat failed (model=%s): %s %r",
            model,
            type(e).__name__,
            e,
            exc_info=True,
        )
        return None


SECTION_SUMMARY_SYSTEM = (
    "You summarise sections of a document for a search index. "
    "You will be given one or more sections in one request, each tagged with an id. "
    "Reply with STRICT JSON only, of the form: "
    '{"sections": [{"id": "<id>", "summary": "<1-2 sentences, <=280 chars>", '
    '"keywords": ["...", "..."]}, ...]}. '
    "Keep 5-8 salient keywords per section (short noun phrases). "
    "Return one entry per input id. No prose outside the JSON."
)


@dataclass
class SectionEnrichment:
    summary: str
    keywords: list[str]


def render_section_for_batch(section: Section, body: str) -> str:
    return f"--- section id: {section.id}\ntitle: {section.title}\ntext:\n{body}\n"


async def enrich_batch(
    client: httpx.AsyncClient, batch: list[Section]
) -> dict[str, SectionEnrichment]:
    bodies: dict[str, str] = {}
    prompt_parts: list[str] = []
    for s in batch:
        body = section_body_text_limited_by_tokens(
            s, settings.metadata_ollama_section_body_tokens
        )
        bodies[s.id] = body
        if body:
            prompt_parts.append(render_section_for_batch(s, body))

    out: dict[str, SectionEnrichment] = {}

    if prompt_parts:
        user = "\n".join(prompt_parts)
        parsed = await ollama_json_chat(
            client,
            model=settings.metadata_model,
            system=SECTION_SUMMARY_SYSTEM,
            user=user,
            timeout=settings.metadata_ollama_enrichment_timeout,
            max_output_tokens=settings.metadata_max_output_tokens,
        )
        items: list[dict[str, Any]] = []
        if isinstance(parsed, dict):
            raw = parsed.get("sections") or parsed.get("items") or []
            if isinstance(raw, list):
                items = [i for i in raw if isinstance(i, dict)]
        elif isinstance(parsed, list):
            items = [i for i in parsed if isinstance(i, dict)]

        for item in items:
            sid = str(item.get("id", "")).strip()
            if not sid:
                continue
            summary = str(item.get("summary", "")).strip()[
                :settings.metadata_ollama_batch_section_summary_max
            ]
            kws_raw = item.get("keywords") or []
            keywords = [str(k).strip() for k in kws_raw if str(k).strip()][
                :settings.metadata_ollama_batch_keywords_max
            ]
            if summary or keywords:
                out[sid] = SectionEnrichment(summary=summary, keywords=keywords)

    for s in batch:
        if s.id in out:
            continue
        body = bodies[s.id]
        if body:
            summary = heuristic_summary(body)
            keywords = heuristic_keywords(body)
        else:
            # Title-only section — fall back to the title itself for keywords
            summary = ""
            keywords = heuristic_keywords(s.title) if s.title else []
        out[s.id] = SectionEnrichment(summary=summary, keywords=keywords)
    return out


async def build_sections_index(root: Section) -> list[dict[str, Any]]:
    sections = walk_sections(root)
    size = max(1, settings.metadata_ollama_batch_size)
    batches: list[list[Section]] = [
        sections[i : i + size] for i in range(0, len(sections), size)
    ]

    sem = asyncio.Semaphore(max(1, settings.metadata_concurrency))

    async with httpx.AsyncClient() as client:

        async def run_batch(batch: list[Section]) -> dict[str, SectionEnrichment]:
            async with sem:
                return await enrich_batch(client, batch)

        batch_results = await asyncio.gather(*[run_batch(b) for b in batches])

    by_id: dict[str, SectionEnrichment] = {}
    for r in batch_results:
        by_id.update(r)

    entries: list[dict[str, Any]] = []
    for section in sections:
        enrichment = by_id.get(section.id, SectionEnrichment(summary="", keywords=[]))
        elc = element_counts(section)
        entries.append(
            {
                "id": section.id,
                "title": section.title,
                "normalized_title": normalize_title(section.title),
                "path": section.path,
                "level": section.level,
                "page_range": list(section.page_range),
                "summary": enrichment.summary,
                "keywords": enrichment.keywords,
                "element_counts": elc,
                "has_tables": elc.get("table", 0) > 0,
                "has_figures": elc.get("image", 0) > 0,
            }
        )
    return entries


DOC_META_SYSTEM = (
    "You are a metadata extractor for academic and professional documents. "
    "Given the first sections of a document and a table of contents, reply "
    "with STRICT JSON: "
    '{"doc_type": "paper|report|contract|article|other", '
    '"language": "<ISO-639-1>", '
    '"inferred_title": "...", '
    '"inferred_authors": ["..."], '
    '"abstract": "<3-5 sentence synopsis>"}'
    " -- omit any field you cannot confidently fill (empty string or empty list)."
)


def collect_figure_table_index(
    root: Section,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    figures: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    for section in walk_sections(root):
        for el in section.elements:
            caption = (
                (el.extra.get("caption") if hasattr(el, "extra") else None)
                or el.text
                or ""
            )
            entry = {
                "caption": (caption or "").strip()[:200],
                "section_id": section.id,
                "section_path": section.path,
                "page": el.page,
            }
            if el.type == "image":
                figures.append(entry)
            elif el.type == "table":
                tables.append(entry)
    return figures, tables


async def build_document_meta(
    root: Section, *, document_id: str, filename: str, num_pages: int
) -> dict[str, Any]:
    sections = walk_sections(root)
    compact_sections = []
    for s in sections[:3]:
        compact_sections.append(
            f"## {s.title}\n{section_body_text(s, settings.metadata_doc_meta_opening_chars)}"
        )
    toc = "\n".join(
        f"- {s.path} (pp. {s.page_range[0]}-{s.page_range[1]})" for s in sections
    )

    user = (
        f"Filename: {filename}\n"
        f"Total pages: {num_pages}\n\n"
        f"Table of contents:\n{toc}\n\n"
        f"Opening sections:\n\n" + "\n\n".join(compact_sections)
    )

    inferred: dict[str, Any] = {}
    async with httpx.AsyncClient() as client:
        parsed = await ollama_json_chat(
            client,
            model=settings.metadata_model,
            system=DOC_META_SYSTEM,
            user=user,
            timeout=settings.metadata_doc_meta_ollama_timeout,
        )
    if isinstance(parsed, dict):
        inferred = parsed

    figures, tables = collect_figure_table_index(root)

    return {
        "document_id": document_id,
        "filename": filename,
        "num_pages": num_pages,
        "doc_type": str(inferred.get("doc_type") or "other").strip().lower(),
        "language": str(inferred.get("language") or "").strip().lower()[:8],
        "inferred_title": str(inferred.get("inferred_title") or "").strip()[:300],
        "inferred_authors": [
            str(a).strip()
            for a in (inferred.get("inferred_authors") or [])
            if str(a).strip()
        ][:20],
        "abstract": str(inferred.get("abstract") or "").strip()[:500],
        "figure_index": figures,
        "table_index": tables,
        "num_sections": len(sections),
    }


FULL_ENRICHMENT_SYSTEM = (
    "You enrich a freshly parsed document for a retrieval system. "
    "You receive a table of contents and per-section text. "
    "Return STRICT JSON with exactly this shape:\n"
    "{\n"
    '  "document": {\n'
    '    "doc_type": "paper|report|contract|article|other",\n'
    '    "language": "<ISO-639-1, e.g. en>",\n'
    '    "inferred_title": "...",\n'
    '    "inferred_authors": ["..."],\n'
    '    "abstract": "<1-2 sentence synopsis, <=360 chars>"\n'
    "  },\n"
    '  "sections": [\n'
    '    {"id": "<exact id from input>", '
    '"summary": "<1 sentence, <=160 chars>", '
    '"keywords": ["...", "..."]}\n'
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- Emit one sections[] entry per input section id (use the exact id, "
    "never invent or duplicate ids).\n"
    "- Keep 3-5 short noun-phrase keywords per section (be concise).\n"
    "- Summaries: ONE sentence, <=160 chars, faithful to the section text; "
    "no hallucinating.\n"
    "- If a section has no usable text, set summary='' and keywords=[].\n"
    "- Output ONLY the JSON object, no prose."
)


def toc_line(s: Section) -> str:
    return (
        f"- id={s.id} | level={s.level} | {s.path} "
        f"(pp. {s.page_range[0]}-{s.page_range[1]})"
    )


def body_block(s: Section) -> str:
    body = section_body_text(s, limit_chars=1200)
    if not body:
        return ""
    return f"### id={s.id} | {s.title}\n{body}"


def render_user_prompt(
    *,
    all_sections: list[Section],
    chunk_sections: list[Section],
    filename: str,
    num_pages: int,
    chunk_idx: int,
    chunk_total: int,
) -> str:
    toc = "\n".join(toc_line(s) for s in all_sections)
    body_blocks = [b for b in (body_block(s) for s in chunk_sections) if b]
    chunk_ids = ", ".join(s.id for s in chunk_sections)

    header_lines = [
        f"Filename: {filename}",
        f"Total pages: {num_pages}",
        f"Total sections: {len(all_sections)}",
    ]
    if chunk_total > 1:
        header_lines.append(
            f"Chunk {chunk_idx + 1} of {chunk_total}. "
            f"Return section entries ONLY for these ids: [{chunk_ids}]."
        )
        if chunk_idx > 0:
            header_lines.append(
                'You may leave "document" as {} in this chunk; '
                "document-level meta is handled separately."
            )

    return (
        "\n".join(header_lines)
        + "\n\nTable of contents (all sections):\n"
        + toc
        + "\n\nSection bodies (this chunk only):\n\n"
        + "\n\n".join(body_blocks)
    )


def pack_section_chunks(
    all_sections: list[Section],
    *,
    filename: str,
    num_pages: int,
    token_budget: int,
) -> list[list[Section]]:
    one_shot = render_user_prompt(
        all_sections=all_sections,
        chunk_sections=all_sections,
        filename=filename,
        num_pages=num_pages,
        chunk_idx=0,
        chunk_total=1,
    )
    if count_tokens(one_shot) <= token_budget:
        return [all_sections]

    chunks: list[list[Section]] = []
    current: list[Section] = []
    for s in all_sections:
        trial = [*current, s]
        rendered = render_user_prompt(
            all_sections=all_sections,
            chunk_sections=trial,
            filename=filename,
            num_pages=num_pages,
            chunk_idx=len(chunks),
            chunk_total=max(2, len(chunks) + 1),
        )
        if count_tokens(rendered) <= token_budget or not current:
            current = trial
        else:
            chunks.append(current)
            current = [s]
    if current:
        chunks.append(current)
    return chunks


def assemble_sections_index(
    sections: list[Section], by_id: dict[str, SectionEnrichment]
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for section in sections:
        enrichment = by_id.get(section.id, SectionEnrichment(summary="", keywords=[]))
        elc = element_counts(section)
        entries.append(
            {
                "id": section.id,
                "title": section.title,
                "normalized_title": normalize_title(section.title),
                "path": section.path,
                "level": section.level,
                "page_range": list(section.page_range),
                "summary": enrichment.summary,
                "keywords": enrichment.keywords,
                "element_counts": elc,
                "has_tables": elc.get("table", 0) > 0,
                "has_figures": elc.get("image", 0) > 0,
            }
        )
    return entries


def assemble_document_meta(
    root: Section,
    *,
    inferred: dict[str, Any],
    document_id: str,
    filename: str,
    num_pages: int,
) -> dict[str, Any]:
    figures, tables = collect_figure_table_index(root)
    return {
        "document_id": document_id,
        "filename": filename,
        "num_pages": num_pages,
        "doc_type": str(inferred.get("doc_type") or "other").strip().lower(),
        "language": str(inferred.get("language") or "").strip().lower()[:8],
        "inferred_title": str(inferred.get("inferred_title") or "").strip()[:300],
        "inferred_authors": [
            str(a).strip()
            for a in (inferred.get("inferred_authors") or [])
            if str(a).strip()
        ][:20],
        "abstract": str(inferred.get("abstract") or "").strip()[:500],
        "figure_index": figures,
        "table_index": tables,
        "num_sections": len(walk_sections(root)),
    }


def heuristic_build_sections_index(
    sections: list[Section],
) -> list[dict[str, Any]]:
    """Build a sections_index using heuristics only — no LLM calls.

    Uses :func:`heuristic_summary` and :func:`heuristic_keywords` on body
    text (or title-only for sections with no body).  Produces the same shape
    as the LLM-based enrichment path so query-time consumers are unaffected.
    """
    by_id: dict[str, SectionEnrichment] = {}
    for s in sections:
        body = section_body_text(s)
        if body:
            summary = heuristic_summary(body)
            keywords = heuristic_keywords(body)
        else:
            summary = ""
            keywords = heuristic_keywords(s.title) if s.title else []
        by_id[s.id] = SectionEnrichment(summary=summary, keywords=keywords)
    return assemble_sections_index(sections, by_id)


def heuristic_build_document_meta(
    root: Section,
    *,
    document_id: str,
    filename: str,
    num_pages: int,
) -> dict[str, Any]:
    """Build document_meta using heuristics only — no LLM calls.

    The figure/table index is always populated from the tree structure.
    LLM-inferred fields (doc_type, language, title, authors, abstract) are
    left empty/default since no model is called.
    """
    return assemble_document_meta(
        root,
        inferred={},
        document_id=document_id,
        filename=filename,
        num_pages=num_pages,
    )


def merge_section_response(
    by_id: dict[str, SectionEnrichment], parsed: dict[str, Any]
) -> None:
    for item in parsed.get("sections") or []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id", "")).strip()
        if not sid:
            continue
        summary = str(item.get("summary", "")).strip()[
            :settings.metadata_openrouter_parsed_section_summary_max
        ]
        kws = [str(k).strip() for k in (item.get("keywords") or []) if str(k).strip()][
            :settings.metadata_openrouter_parsed_keywords_max
        ]
        by_id[sid] = SectionEnrichment(summary=summary, keywords=kws)


def partition_openrouter_chunk_results(
    results: list[Any | BaseException], num_chunks: int
) -> tuple[bool, dict[int, dict[str, Any]]]:
    any_ok = False
    by_idx: dict[int, dict[str, Any]] = {}
    for r in results:
        if isinstance(r, BaseException):
            log.warning("enrichment chunk raised: %s", r)
            continue
        idx, parsed = r
        if parsed is None:
            log.warning(
                "enrichment chunk %d/%d returned no JSON; "
                "filling its sections with heuristics",
                idx + 1,
                num_chunks,
            )
            continue
        by_idx[idx] = parsed
        any_ok = True
    return any_ok, by_idx


def merge_parsed_openrouter_index(
    by_id: dict[str, SectionEnrichment], parsed_by_idx: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    doc_inferred: dict[str, Any] = {}
    for idx in sorted(parsed_by_idx):
        parsed = parsed_by_idx[idx]
        merge_section_response(by_id, parsed)
        doc_block = parsed.get("document") or {}
        if isinstance(doc_block, dict) and not doc_inferred:
            doc_inferred = doc_block
    return doc_inferred


async def openrouter_enrich_one_chunk(
    idx: int,
    chunk_sections: list[Section],
    *,
    all_sections: list[Section],
    filename: str,
    num_pages: int,
    chunk_total: int,
) -> tuple[int, dict[str, Any] | None]:
    user = render_user_prompt(
        all_sections=all_sections,
        chunk_sections=chunk_sections,
        filename=filename,
        num_pages=num_pages,
        chunk_idx=idx,
        chunk_total=chunk_total,
    )
    parsed = await openrouter_json(
        model=settings.metadata_openrouter_model,
        system=FULL_ENRICHMENT_SYSTEM,
        user=user,
        timeout=settings.metadata_openrouter_enrichment_timeout,
        temperature=settings.metadata_openrouter_enrichment_temperature,
    )
    return idx, parsed if isinstance(parsed, dict) else None


async def enrich_via_openrouter(
    root: Section, *, document_id: str, filename: str, num_pages: int
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    if not settings.openrouter_api_key:
        log.warning(
            "settings.metadata_provider=openrouter but settings.openrouter_api_key is empty; "
            "falling back to Ollama batched enrichment."
        )
        return None

    sections = walk_sections(root)
    if not sections:
        return [], assemble_document_meta(
            root,
            inferred={},
            document_id=document_id,
            filename=filename,
            num_pages=num_pages,
        )

    chunks = pack_section_chunks(
        sections,
        filename=filename,
        num_pages=num_pages,
        token_budget=settings.metadata_openrouter_input_token_budget,
    )
    log.info(
        "enrichment: %d section(s) -> %d OpenRouter call(s) (budget=%d tokens)",
        len(sections),
        len(chunks),
        settings.metadata_openrouter_input_token_budget,
    )

    by_id: dict[str, SectionEnrichment] = {}
    n = len(chunks)
    sem = asyncio.Semaphore(max(1, settings.metadata_concurrency))

    async def _one_chunk(i: int, c: list[Section]) -> tuple[int, dict[str, Any] | None]:
        async with sem:
            return await openrouter_enrich_one_chunk(
                i,
                c,
                all_sections=sections,
                filename=filename,
                num_pages=num_pages,
                chunk_total=n,
            )

    results = await asyncio.gather(
        *(_one_chunk(i, c) for i, c in enumerate(chunks)),
        return_exceptions=True,
    )

    any_chunk_parsed, parsed_by_idx = partition_openrouter_chunk_results(results, n)
    if not any_chunk_parsed:
        log.warning("all enrichment chunks failed; falling back to Ollama path")
        return None

    doc_inferred = merge_parsed_openrouter_index(by_id, parsed_by_idx)

    for s in sections:
        if s.id in by_id:
            continue
        body = section_body_text(s, limit_chars=1200)
        if body:
            summary = heuristic_summary(body)
            keywords = heuristic_keywords(body)
        else:
            # Title-only section — fall back to the title itself for keywords
            # so the section is at least findable by name in the router.
            summary = ""
            keywords = heuristic_keywords(s.title) if s.title else []
        by_id[s.id] = SectionEnrichment(summary=summary, keywords=keywords)

    sections_index = assemble_sections_index(sections, by_id)
    doc_meta = assemble_document_meta(
        root,
        inferred=doc_inferred,
        document_id=document_id,
        filename=filename,
        num_pages=num_pages,
    )
    return sections_index, doc_meta


async def build_enrichment(
    root: Section, *, document_id: str, filename: str, num_pages: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if settings.metadata_provider == "openrouter":
        result = await enrich_via_openrouter(
            root,
            document_id=document_id,
            filename=filename,
            num_pages=num_pages,
        )
        if result is not None:
            return result

    sections_index = await build_sections_index(root)
    doc_meta = await build_document_meta(
        root, document_id=document_id, filename=filename, num_pages=num_pages
    )
    return sections_index, doc_meta
