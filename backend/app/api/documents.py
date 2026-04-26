from __future__ import annotations

from typing import Any

from app import document_data
from app.config import MAX_DOCS_PER_CHAT


def resolve_chat_document_ids(req: Any) -> list[str]:
    raw: list[str] = []
    if req.document_ids is not None:
        raw = [s.strip() for s in req.document_ids if s and s.strip()]
    if not raw and req.document_id and str(req.document_id).strip():
        raw = [str(req.document_id).strip()]
    if not raw:
        raise ValueError(
            "Provide `document_id` or a non-empty `document_ids` list for chat"
        )
    out: list[str] = []
    seen: set[str] = set()
    for x in raw:
        if x not in seen:
            seen.add(x)
            out.append(x)
    if len(out) > MAX_DOCS_PER_CHAT:
        raise ValueError(
            f"At most {MAX_DOCS_PER_CHAT} documents per chat (got {len(out)})"
        )
    return out


def doc_label(filename: str, doc_id: str) -> str:
    if filename.strip():
        return f'"{filename}"'
    return doc_id


async def readiness_error_for_documents(doc_ids: list[str]) -> str | None:
    problems: list[str] = []
    for did in doc_ids:
        s = await document_data.get_status(did)
        if s is None:
            problems.append(f"{did}: unknown document_id (upload the PDF again)")
            continue
        if s.status == "error":
            detail = s.error or "unknown error"
            label = doc_label(s.filename, did)
            problems.append(f"{label}: processing failed ({detail})")
        elif s.status != "ready":
            progress_pct = int(s.progress * 100)
            label = doc_label(s.filename, did)
            problems.append(f"{label}: not ready — {s.stage} ({progress_pct}%)")
    if not problems:
        return None
    if len(problems) == 1:
        return problems[0]
    return "Not all documents are ready. " + "; ".join(problems)


def search_hits_to_results(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_id": h.get("chunk_id"),
            "section_path": h.get("section_path"),
            "page": h.get("page"),
            "type": h.get("type"),
            "score": h.get("_score"),
            "preview": (h.get("display_text") or "")[:240],
            "bbox": h.get("bbox"),
            "page_size": h.get("page_size"),
        }
        for h in hits
    ]
