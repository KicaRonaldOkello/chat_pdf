from __future__ import annotations

from typing import Any

from app.processing.structure import Section


def serialize(
    root: Section,
    *,
    document_id: str,
    filename: str,
    num_pages: int,
) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "filename": filename,
        "num_pages": num_pages,
        "sections": (
            [c.to_dict() for c in root.children] if root.children else [root.to_dict()]
        ),
    }


def walk_sections(root: Section) -> list[Section]:
    out: list[Section] = []
    stack: list[Section] = [root]
    while stack:
        s = stack.pop()
        if s is not root:
            out.append(s)
        stack.extend(reversed(s.children))
    return out
