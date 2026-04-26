from __future__ import annotations

from typing import Any

from app.config import RETRIEVAL_TOP_K
from app.processing import embeddings, vectorstore


def format_chunk(ch: dict[str, Any]) -> str:
    header = f"[p.{ch.get('page', '?')} | {ch.get('section_path', '')}]"
    return f"{header}\n{ch.get('display_text', '')}"


async def build_context(
    document_id: str | list[str], query: str, top_k: int = RETRIEVAL_TOP_K
) -> str:
    vector = await embeddings.embed_query(query)
    if not vector:
        return ""
    hits = await vectorstore.search(document_id, vector, top_k)
    if not hits:
        return ""

    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for h in hits:
        key = h.get("section_path") or "(root)"
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(h)

    blocks: list[str] = []
    for section in order:
        rows = grouped[section]
        rows.sort(key=lambda r: (r.get("page", 0), -r.get("_score", 0)))
        blocks.append(f"## {section}")
        for r in rows:
            blocks.append(format_chunk(r))
    return "\n\n".join(blocks)
