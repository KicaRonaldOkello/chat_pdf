"""Unit tests for image pipeline helpers (no PDF I/O, no network)."""

from __future__ import annotations

import json

import pytest

from app.processing.images import (
    VisionCaption,
    bbox_overlap,
    find_section_for_page,
    match_image,
    parse_caption_json,
)
from app.processing.structure import ElementRef, Section


def test_bbox_overlap_disjoint() -> None:
    assert (
        bbox_overlap([0.0, 0.0, 1.0, 1.0], [2.0, 2.0, 3.0, 3.0]) == 0.0
    )


def test_bbox_overlap_full_cover() -> None:
    # identical boxes -> intersection / area = 1
    box = [0.0, 0.0, 10.0, 10.0]
    assert bbox_overlap(box, box) == pytest.approx(1.0)


def test_bbox_overlap_partial() -> None:
    a = [0.0, 0.0, 10.0, 10.0]
    b = [5.0, 5.0, 15.0, 15.0]  # quarter of a overlaps
    assert bbox_overlap(a, b) == pytest.approx(0.25)


def test_parse_caption_json_strips_fences() -> None:
    raw = '```json\n{"caption": "C", "description": "D text"}\n```'
    cap = parse_caption_json(raw)
    assert cap.caption == "C"
    assert cap.description == "D text"


def test_parse_caption_json_fallback_non_json() -> None:
    raw = "line one\nline two here"
    cap = parse_caption_json(raw)
    assert cap.caption == "line one"
    assert "line two" in cap.description


def test_parse_caption_json_invalid_dict_returns_empty() -> None:
    cap = parse_caption_json(json.dumps(["not", "a", "dict"]))
    assert cap.caption == ""
    assert cap.description == ""


def test_vision_caption_coerce_list_to_str() -> None:
    v = VisionCaption.model_validate({"caption": ["a", "b"], "description": None})
    assert v.caption == "a b"
    assert v.description == ""


def test_match_image_prefers_overlap() -> None:
    fig = {"page": 1, "bbox": [0.0, 0.0, 10.0, 10.0]}
    ph_good = ElementRef(
        id="g",
        type="image",
        page=1,
        text="",
        bbox=[0.0, 0.0, 10.0, 10.0],
    )
    ph_far = ElementRef(
        id="f",
        type="image",
        page=1,
        text="",
        bbox=[100.0, 100.0, 101.0, 101.0],
    )
    got = match_image(fig, [ph_far, ph_good], set())
    assert got is ph_good


def test_match_image_falls_back_same_page_when_low_overlap() -> None:
    fig = {"page": 2, "bbox": [0.0, 0.0, 1.0, 1.0]}
    ph = ElementRef(
        id="p",
        type="image",
        page=2,
        text="",
        bbox=[50.0, 50.0, 51.0, 51.0],
    )
    got = match_image(fig, [ph], set())
    assert got is ph


def test_find_section_for_page_picks_deepest_covering() -> None:
    root = Section(
        id="r",
        title="R",
        level=0,
        path="Doc",
        page_range=[1, 10],
        elements=[],
        children=[
            Section(
                id="c1",
                title="A",
                level=1,
                path="Doc > A",
                page_range=[1, 10],
                elements=[],
                children=[
                    Section(
                        id="c2",
                        title="B",
                        level=2,
                        path="Doc > A > B",
                        page_range=[3, 4],
                        elements=[],
                    )
                ],
            )
        ],
    )
    sec = find_section_for_page(root, page=3)
    assert sec.path == "Doc > A > B"
