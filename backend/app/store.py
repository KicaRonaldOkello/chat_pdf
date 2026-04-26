from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.config import DOCUMENTS_DIR

Status = str


@dataclass
class DocumentStatus:
    status: Status
    stage: str
    progress: float
    filename: str
    error: str | None = None
    num_pages: int | None = None
    warnings: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def doc_dir(doc_id: str) -> Path:
    return DOCUMENTS_DIR / doc_id


def status_path(doc_id: str) -> Path:
    return doc_dir(doc_id) / "status.json"


def tree_path(doc_id: str) -> Path:
    return doc_dir(doc_id) / "tree.json"


def sections_index_path(doc_id: str) -> Path:
    return doc_dir(doc_id) / "sections_index.json"


def document_meta_path(doc_id: str) -> Path:
    return doc_dir(doc_id) / "document_meta.json"


def traces_dir(doc_id: str) -> Path:
    d = doc_dir(doc_id) / "traces"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pdf_path(doc_id: str) -> Path:
    return doc_dir(doc_id) / "source.pdf"


def images_dir(doc_id: str) -> Path:
    d = doc_dir(doc_id) / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_upload(data: bytes, filename: str) -> str:
    doc_id = str(uuid.uuid4())
    d = doc_dir(doc_id)
    d.mkdir(parents=True, exist_ok=True)
    pdf_path(doc_id).write_bytes(data)
    set_status(
        doc_id,
        DocumentStatus(
            status="queued", stage="queued", progress=0.0, filename=filename
        ),
    )
    return doc_id


def set_status(doc_id: str, status: DocumentStatus) -> None:
    status_path(doc_id).write_text(json.dumps(status.to_dict(), indent=2))


def update_status(doc_id: str, **kwargs: Any) -> DocumentStatus:
    current = get_status(doc_id)
    if current is None:
        raise KeyError(f"Unknown document_id: {doc_id}")
    merged = {**current.to_dict(), **kwargs}
    new = DocumentStatus(
        status=merged.get("status", current.status),
        stage=merged.get("stage", current.stage),
        progress=float(merged.get("progress", current.progress)),
        filename=merged.get("filename", current.filename),
        error=merged.get("error"),
        num_pages=merged.get("num_pages"),
        warnings=merged.get("warnings", current.warnings),
    )
    set_status(doc_id, new)
    return new


def get_status(doc_id: str) -> DocumentStatus | None:
    p = status_path(doc_id)
    if not p.exists():
        return None
    raw = json.loads(p.read_text())
    w = raw.get("warnings")
    if w is not None and not isinstance(w, list):
        w = None
    return DocumentStatus(
        status=raw["status"],
        stage=raw.get("stage", raw["status"]),
        progress=float(raw.get("progress", 0.0)),
        filename=raw.get("filename", ""),
        error=raw.get("error"),
        num_pages=raw.get("num_pages"),
        warnings=[str(x) for x in w] if w else None,
    )


def save_tree(doc_id: str, tree: dict[str, Any]) -> None:
    tree_path(doc_id).write_text(json.dumps(tree, indent=2, ensure_ascii=False))


def get_tree(doc_id: str) -> dict[str, Any] | None:
    p = tree_path(doc_id)
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    return data if isinstance(data, dict) else None


def save_sections_index(doc_id: str, entries: list[dict[str, Any]]) -> None:
    sections_index_path(doc_id).write_text(
        json.dumps(entries, indent=2, ensure_ascii=False)
    )


def get_sections_index(doc_id: str) -> list[dict[str, Any]] | None:
    p = sections_index_path(doc_id)
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    return data if isinstance(data, list) else None


def save_document_meta(doc_id: str, meta: dict[str, Any]) -> None:
    document_meta_path(doc_id).write_text(
        json.dumps(meta, indent=2, ensure_ascii=False)
    )


def get_document_meta(doc_id: str) -> dict[str, Any] | None:
    p = document_meta_path(doc_id)
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    return data if isinstance(data, dict) else None


def append_trace(doc_id: str, trace: dict[str, Any]) -> Path:
    from datetime import datetime

    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    path = traces_dir(doc_id) / f"{ts}.json"
    path.write_text(json.dumps(trace, indent=2, ensure_ascii=False))
    return path


def list_traces(doc_id: str, limit: int = 20) -> list[dict[str, Any]]:
    d = doc_dir(doc_id) / "traces"
    if not d.exists():
        return []
    files = sorted(d.glob("*.json"), reverse=True)[:limit]
    out: list[dict[str, Any]] = []
    for f in files:
        try:
            out.append(json.loads(f.read_text()))
        except Exception:
            continue
    return out


def delete_document(doc_id: str) -> None:
    shutil.rmtree(doc_dir(doc_id), ignore_errors=True)
