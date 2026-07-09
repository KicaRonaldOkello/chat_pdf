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


def deserialize(tree_data: dict[str, Any]) -> Section:
    """Reconstruct a Section tree from a ``serialize()``-produced dict.

    Returns a synthetic root whose children are the stored top-level sections,
    matching the shape expected by ``walk_sections`` (which skips the root).
    """
    section_dicts: list[dict[str, Any]] = tree_data.get("sections", [])
    root = Section(
        id="sec-root",
        title="(root)",
        level=0,
        path="",
        page_range=[1, 1],
    )
    root.children = [Section.from_dict(s) for s in section_dicts]
    return root


def walk_sections(root: Section) -> list[Section]:
    out: list[Section] = []
    stack: list[Section] = [root]
    while stack:
        s = stack.pop()
        if s is not root:
            out.append(s)
        stack.extend(reversed(s.children))
    return out
