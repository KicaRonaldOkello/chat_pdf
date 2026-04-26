from __future__ import annotations

import asyncio
import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator

from app import s3_storage
from app.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    SLOW_UPSTREAM_REQUEST_TIMEOUT,
    VISION_MODEL,
)
from app.processing.structure import ElementRef, Section

CAPTION_PROMPT = (
    "Describe this figure from an uploaded document for a retrieval index. "
    "Return STRICT JSON with two keys:\n"
    '  "caption": a short title-like phrase (<= 12 words)\n'
    '  "description": 2-3 sentences stating what the figure shows, the type '
    "of visual (diagram, chart, photo, schematic, heatmap, etc.), the axes "
    "or components if relevant, and any labels or legends visible.\n"
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
        key = s3_storage.put_image_bytes(
            document_id, fig["rel_name"], fig["png_bytes"]
        )
        fig["s3_key"] = key

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
        ph.extra["path"] = str(fig.get("s3_key", ""))
        pairings.append((ph, fig))

    if not OPENROUTER_API_KEY:
        for ph, _ in pairings:
            ph.extra.setdefault("caption", ph.text)
            ph.extra.setdefault("description", "")
        return

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[caption_one(client, fig["png_bytes"]) for _, fig in pairings]
        )
    for (ph, _), caption in zip(pairings, results, strict=False):
        ph.extra["caption"] = caption.caption or ph.text
        ph.extra["description"] = caption.description
