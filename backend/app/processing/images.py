from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from app.storage import get_storage
from app.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    SLOW_UPSTREAM_REQUEST_TIMEOUT,
    VISION_MODEL,
)
from app.processing.structure import ElementRef, Section
from app.processing.tree import walk_sections

CAPTION_PROMPT = (
    "Describe this figure from an uploaded document for a retrieval index. "
    "Return STRICT JSON with two keys:\n"
    '  "caption": a short title-like phrase (<= 12 words)\n'
    '  "description": 2-3 sentences stating what the figure shows, the type '
    "of visual (diagram, chart, photo, schematic, heatmap, etc.), the axes "
    "or components if relevant, and any labels or legends visible.\n"
    "Do not include markdown fences. JSON only."
)

QA_VISION_PROMPT = (
    "You are analyzing a page from a PDF to help answer the user's question.\n\n"
    "User question: {query}\n\n"
    "Look at the page image and return STRICT JSON with:\n"
    '  "relevant_text": any visible text on the page that relates to the question\n'
    '  "visual_elements": describe charts, diagrams, tables, signatures, stamps, '
    " handwriting, or other visual content relevant to the question\n"
    '  "observations": factual observations that help answer the question\n'
    '  "confidence": one of "high", "medium", or "low"\n\n'
    "For charts/tables: read axes, legends, labels, approximate values, trends.\n"
    "For signatures/stamps: note whether visible; do not infer identity unless "
    "text is clearly legible.\n"
    "If the page contains nothing relevant to the question, say so plainly.\n"
    "Do not include markdown fences. JSON only."
)


class VisionCaption(BaseModel):
    caption: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=1500)

    model_config = {"extra": "ignore", "str_strip_whitespace": True}

    @field_validator("caption", "description", mode="before")
    @classmethod
    def coerce_to_str(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return " ".join(str(x) for x in v)
        return str(v)

    @staticmethod
    def empty() -> VisionCaption:
        return VisionCaption(caption="", description="")


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


def render_images(
    pdf_file: Path, out_dir: Path, min_side_px: int = 120
) -> list[dict[str, Any]]:
    import fitz  # PyMuPDF

    results: list[dict[str, Any]] = []
    doc = fitz.open(pdf_file)
    try:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_num = page_idx + 1
            page_rect = page.rect
            page_size = [float(page_rect.width), float(page_rect.height)]
            infos = page.get_image_info(xrefs=True)
            for i, info in enumerate(infos):
                xref = info.get("xref")
                bbox = info.get("bbox")
                if not xref or not bbox:
                    continue
                width = info.get("width", 0) or 0
                height = info.get("height", 0) or 0
                if width < min_side_px or height < min_side_px:
                    continue
                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.n - pix.alpha >= 4:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    rel_name = f"p{page_num:04d}_{i:02d}.png"
                    out_path = out_dir / rel_name
                    pix.save(str(out_path))
                    pix = None
                    png_bytes = out_path.read_bytes()
                except Exception:
                    continue
                results.append(
                    {
                        "page": page_num,
                        "bbox": [float(b) for b in bbox],
                        "page_size": page_size,
                        "rel_name": rel_name,
                        "png_bytes": png_bytes,
                    }
                )
    finally:
        doc.close()
    return results


def render_page_image(
    doc_id: str, page: int, *, dpi: int = 200
) -> bytes:
    """Render a full PDF page as a PNG image.

    Pulls the source PDF from storage, renders *page* (1-based) with
    PyMuPDF at *dpi*, and returns PNG bytes.  Used at query time for
    on-demand visual analysis of pages that may contain charts, diagrams,
    signatures, or other non-text elements.
    """
    import fitz

    pdf_bytes = get_storage().get_source_pdf_bytes(doc_id)
    # PyMuPDF can open directly from a bytes stream — no temp file needed.
    doc = None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_obj = doc[page - 1]  # 0-based
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page_obj.get_pixmap(matrix=mat)
        return pix.tobytes("png")
    finally:
        if doc is not None:
            doc.close()


async def analyze_page_for_query(
    doc_id: str,
    page: int,
    query: str,
    *,
    dpi: int = 200,
) -> str | None:
    """Render a page and ask the vision model to analyse it for *query*.

    Returns a human-readable analysis block, or ``None`` if the vision
    model is unavailable or the page cannot be rendered.
    """
    import base64

    if not OPENROUTER_API_KEY:
        return None

    try:
        png_bytes = await asyncio.to_thread(
            render_page_image, doc_id, page, dpi=dpi
        )
    except Exception as e:
        logger.warning(f"Failed to render page {page} for doc {doc_id}: {e}")
        return None

    data_url = f"data:image/png;base64,{base64.b64encode(png_bytes).decode()}"
    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": QA_VISION_PROMPT.format(query=query)},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=SLOW_UPSTREAM_REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            raw = str(data["choices"][0]["message"]["content"])
    except Exception as e:
        logger.warning(f"Vision API call failed for doc {doc_id} page {page}: {e}")
        return None

    # Parse the JSON response into a readable block
    try:
        import re as _re

        text = raw.strip()
        text = _re.sub(
            r"^```(?:json)?\s*|\s*```$", "", text, flags=_re.IGNORECASE | _re.MULTILINE
        )
        obj = json.loads(text)
    except Exception:
        return f"## Visual analysis — p.{page}\n(Vision model returned unparseable output.)"

    confidence = str(obj.get("confidence", "medium")).lower()
    lines = [f"## Visual analysis — p.{page}  (confidence: {confidence})"]
    for key, label in [
        ("relevant_text", "Visible text"),
        ("visual_elements", "Visual content"),
        ("observations", "Observations"),
    ]:
        val = str(obj.get(key, "")).strip()
        if val:
            lines.append(f"**{label}**: {val}")
    return "\n".join(lines)


def parse_caption_json(raw: str) -> VisionCaption:
    text = raw.strip()
    text = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE
    )
    try:
        obj = json.loads(text)
    except Exception:
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        obj = {
            "caption": lines[0] if lines else "",
            "description": " ".join(lines[1:]) if len(lines) > 1 else "",
        }
    if not isinstance(obj, dict):
        return VisionCaption.empty()
    try:
        return VisionCaption.model_validate(obj)
    except ValidationError:
        return VisionCaption.empty()


async def caption_one(
    client: httpx.AsyncClient,
    image_bytes: bytes,
) -> VisionCaption:
    try:
        if not image_bytes:
            return VisionCaption.empty()
        data_url = f"data:image/png;base64,{base64.b64encode(image_bytes).decode()}"
    except Exception:
        return VisionCaption.empty()

    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": CAPTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        r = await client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=SLOW_UPSTREAM_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        raw = str(data["choices"][0]["message"]["content"])
        return parse_caption_json(raw)
    except Exception:
        return VisionCaption.empty()


def match_image(
    fig: dict[str, Any],
    image_placeholders: list[ElementRef],
    used: set[str],
) -> ElementRef | None:
    best: ElementRef | None = None
    best_score = 0.0
    for ph in image_placeholders:
        if ph.id in used or ph.page != fig["page"]:
            continue
        if not ph.bbox:
            continue
        score = bbox_overlap(ph.bbox, fig["bbox"])
        if score > best_score:
            best_score = score
            best = ph
    if best is not None and best_score > 0.05:
        return best
    for ph in image_placeholders:
        if ph.id not in used and ph.page == fig["page"]:
            return ph
    return None


def find_section_for_page(root: Section, page: int) -> Section:
    best = root
    stack = [root]
    while stack:
        s = stack.pop()
        if s is not root:
            lo, hi = s.page_range
            if lo <= page <= hi and s.level > best.level:
                best = s
        stack.extend(s.children)
    return best


async def enrich_images(
    pdf_file: Path,
    document_id: str,
    placeholders: list[ElementRef],
    root: Section,
    el_id_start: int,
) -> None:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="chatpdf-img-") as tmp:
        out_dir = Path(tmp)
        figs = await asyncio.to_thread(render_images, pdf_file, out_dir)
    if not figs:
        for image_placeholder in [p for p in placeholders if p.type == "image"]:
            image_placeholder.extra.setdefault("path", "")
            image_placeholder.extra.setdefault("caption", image_placeholder.text)
            image_placeholder.extra.setdefault("description", "")
        return

    for fig in figs:
        key = get_storage().put_image_bytes(
            document_id, fig["rel_name"], fig["png_bytes"]
        )
        fig["storage_key"] = key

    image_placeholders = [p for p in placeholders if p.type == "image"]
    used_ids: set[str] = set()
    pairings: list[tuple[ElementRef, dict[str, Any]]] = []

    for fig in figs:
        ph = match_image(fig, image_placeholders, used_ids)
        if ph is None:
            el_id_start += 1
            ph = ElementRef(
                id=f"el-{el_id_start}",
                type="image",
                page=fig["page"],
                text="",
                bbox=fig["bbox"],
                page_size=fig.get("page_size"),
            )
            sec = find_section_for_page(root, fig["page"])
            sec.elements.append(ph)
            placeholders.append(ph)
        used_ids.add(ph.id)
        ph.extra["path"] = str(fig.get("storage_key", ""))
        pairings.append((ph, fig))

    # Record image metadata without calling the vision model.
    # Vision analysis is deferred to query time (Phase D-G).
    # Pre-compute nearby text from the same page so image chunks have
    # meaningful embedding signals even before vision runs.
    _page_text_cache: dict[int, str] = {}
    for section in walk_sections(root):
        for el in section.elements:
            if el.type in ("text",) and el.text:
                p = el.page
                existing = _page_text_cache.get(p, "")
                if len(existing) < 600:
                    _page_text_cache[p] = (existing + " " + el.text)[:600]

    for ph, _ in pairings:
        ph.extra.setdefault("caption", ph.text)
        ph.extra.setdefault("description", "")
        ph.extra["vision_analyzed"] = False
        nearby = _page_text_cache.get(ph.page, "")
        if nearby:
            ph.extra["nearby_text"] = nearby.strip()
