"""Tests for enrichment fallback: deserialization, heuristic builders, and
lazy reconstruction from the stored structure tree."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.document_data as document_data
from app.processing.structure import ElementRef, Section
from app.processing.tree import deserialize, serialize, walk_sections

# ---------------------------------------------------------------------------
# ElementRef.from_dict
# ---------------------------------------------------------------------------


class TestElementRefFromDict:
    def test_round_trip_with_bbox_and_extra(self):
        original = ElementRef(
            id="el-1",
            type="text",
            page=3,
            text="hello world",
            bbox=[10.0, 20.0, 100.0, 200.0],
            page_size=[612.0, 792.0],
            extra={"html": "<p>hi</p>", "caption": "Fig 1"},
        )
        # Simulate what Section.to_dict does for an element
        serialized = {
            "id": original.id,
            "type": original.type,
            "page": original.page,
            "text": original.text,
            "bbox": original.bbox,
            "page_size": original.page_size,
            **original.extra,
        }
        restored = ElementRef.from_dict(serialized)
        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.page == original.page
        assert restored.text == original.text
        assert restored.bbox == original.bbox
        assert restored.page_size == original.page_size
        assert restored.extra == original.extra

    def test_round_trip_minimal(self):
        original = ElementRef(id="el-2", type="image", page=1, text="")
        serialized = {
            "id": original.id,
            "type": original.type,
            "page": original.page,
            "text": original.text,
        }
        restored = ElementRef.from_dict(serialized)
        assert restored.id == "el-2"
        assert restored.type == "image"
        assert restored.page == 1
        assert restored.text == ""
        assert restored.bbox is None
        assert restored.page_size is None
        assert restored.extra == {}

    def test_extra_fields_separated(self):
        data = {
            "id": "el-3",
            "type": "table",
            "page": 5,
            "text": "",
            "html": "<table>...</table>",
            "caption": "Table 2",
        }
        restored = ElementRef.from_dict(data)
        assert restored.bbox is None
        assert restored.page_size is None
        assert restored.extra == {"html": "<table>...</table>", "caption": "Table 2"}

    def test_missing_page_defaults_to_one(self):
        data = {"id": "el-4", "type": "text", "text": "no page field"}
        restored = ElementRef.from_dict(data)
        assert restored.page == 1


# ---------------------------------------------------------------------------
# Section.from_dict
# ---------------------------------------------------------------------------


class TestSectionFromDict:
    def test_round_trip_flat(self):
        original = Section(
            id="sec-1",
            title="Introduction",
            level=1,
            path="Introduction",
            page_range=[1, 3],
            elements=[
                ElementRef(id="el-1", type="text", page=1, text="Some text."),
                ElementRef(
                    id="el-2",
                    type="image",
                    page=2,
                    text="",
                    bbox=[0, 0, 100, 100],
                    extra={"caption": "Fig 1"},
                ),
            ],
        )
        restored = Section.from_dict(original.to_dict())
        assert restored.id == original.id
        assert restored.title == original.title
        assert restored.level == original.level
        assert restored.path == original.path
        assert restored.page_range == original.page_range
        assert len(restored.elements) == 2
        assert restored.elements[0].id == "el-1"
        assert restored.elements[0].text == "Some text."
        assert restored.elements[1].extra == {"caption": "Fig 1"}
        assert restored.children == []

    def test_round_trip_nested(self):
        child = Section(
            id="sec-2",
            title="Subsection",
            level=2,
            path="Introduction > Subsection",
            page_range=[2, 2],
            elements=[ElementRef(id="el-3", type="text", page=2, text="Nested.")],
        )
        parent = Section(
            id="sec-1",
            title="Introduction",
            level=1,
            path="Introduction",
            page_range=[1, 3],
            children=[child],
        )
        restored = Section.from_dict(parent.to_dict())
        assert len(restored.children) == 1
        assert restored.children[0].id == "sec-2"
        assert restored.children[0].title == "Subsection"
        assert restored.children[0].elements[0].text == "Nested."


# ---------------------------------------------------------------------------
# tree.deserialize
# ---------------------------------------------------------------------------


class TestTreeDeserialize:
    def test_round_trip(self):
        """serialize → deserialize should produce a walkable tree."""
        root = Section(
            id="sec-root",
            title="(root)",
            level=0,
            path="",
            page_range=[1, 5],
        )
        root.children = [
            Section(
                id="sec-1",
                title="Intro",
                level=1,
                path="Intro",
                page_range=[1, 2],
                elements=[ElementRef(id="el-1", type="text", page=1, text="Hi.")],
            ),
            Section(
                id="sec-2",
                title="Methods",
                level=1,
                path="Methods",
                page_range=[3, 5],
                children=[
                    Section(
                        id="sec-2a",
                        title="Setup",
                        level=2,
                        path="Methods > Setup",
                        page_range=[3, 4],
                    ),
                ],
            ),
        ]

        tree_data = serialize(root, document_id="d1", filename="f.pdf", num_pages=5)
        restored_root = deserialize(tree_data)
        sections = walk_sections(restored_root)

        assert len(sections) == 3  # Intro, Methods, Setup
        ids = {s.id for s in sections}
        assert ids == {"sec-1", "sec-2", "sec-2a"}

        intro = next(s for s in sections if s.id == "sec-1")
        assert intro.title == "Intro"
        assert intro.page_range == [1, 2]
        assert len(intro.elements) == 1

    def test_empty_sections(self):
        tree_data = {
            "document_id": "d1",
            "filename": "f.pdf",
            "num_pages": 1,
            "sections": [],
        }
        root = deserialize(tree_data)
        assert walk_sections(root) == []


# ---------------------------------------------------------------------------
# heuristic_build_sections_index
# ---------------------------------------------------------------------------


class TestHeuristicBuildSectionsIndex:
    def test_shape(self):
        from app.processing.metadata import heuristic_build_sections_index

        sections = [
            Section(
                id="sec-1",
                title="Introduction",
                level=1,
                path="Introduction",
                page_range=[1, 2],
                elements=[
                    ElementRef(
                        id="el-1",
                        type="text",
                        page=1,
                        text="This is the first sentence. And the second.",
                    ),
                    ElementRef(id="el-2", type="image", page=2, text=""),
                ],
            ),
            Section(
                id="sec-2",
                title="Methods",
                level=1,
                path="Methods",
                page_range=[3, 5],
                elements=[
                    ElementRef(
                        id="el-3",
                        type="table",
                        page=3,
                        text="",
                        extra={"html": "<table>...</table>"},
                    ),
                ],
            ),
        ]

        result = heuristic_build_sections_index(sections)
        assert len(result) == 2

        for entry in result:
            for key in (
                "id",
                "title",
                "normalized_title",
                "path",
                "level",
                "page_range",
                "summary",
                "keywords",
                "element_counts",
                "has_tables",
                "has_figures",
            ):
                assert key in entry, f"missing key {key!r}"

        intro = result[0]
        assert intro["id"] == "sec-1"
        assert intro["has_figures"] is True
        assert intro["has_tables"] is False
        assert intro["element_counts"] == {"text": 1, "image": 1}
        # Heuristic summary should pick up first sentence(s)
        assert "first sentence" in intro["summary"].lower()
        assert isinstance(intro["keywords"], list)

        methods = result[1]
        assert methods["has_tables"] is True
        assert methods["has_figures"] is False

    def test_title_only_section(self):
        """Section with no body text should get empty summary and title-derived keywords."""
        from app.processing.metadata import heuristic_build_sections_index

        sections = [
            Section(
                id="sec-1",
                title="Acknowledgments",
                level=1,
                path="Acknowledgments",
                page_range=[10, 10],
                elements=[],
            ),
        ]
        result = heuristic_build_sections_index(sections)
        assert len(result) == 1
        assert result[0]["summary"] == ""
        assert isinstance(result[0]["keywords"], list)


# ---------------------------------------------------------------------------
# heuristic_build_document_meta
# ---------------------------------------------------------------------------


class TestHeuristicBuildDocumentMeta:
    def test_shape(self):
        from app.processing.metadata import heuristic_build_document_meta

        root = Section(
            id="sec-root", title="(root)", level=0, path="", page_range=[1, 5]
        )
        root.children = [
            Section(
                id="sec-1",
                title="Intro",
                level=1,
                path="Intro",
                page_range=[1, 2],
                elements=[
                    ElementRef(
                        id="el-1",
                        type="image",
                        page=1,
                        text="",
                        extra={"caption": "Fig 1"},
                    ),
                    ElementRef(
                        id="el-2",
                        type="table",
                        page=2,
                        text="",
                        extra={"html": "<table>..."},
                    ),
                ],
            ),
        ]

        meta = heuristic_build_document_meta(
            root, document_id="d1", filename="test.pdf", num_pages=5
        )

        assert meta["document_id"] == "d1"
        assert meta["filename"] == "test.pdf"
        assert meta["num_pages"] == 5
        assert meta["doc_type"] == "other"
        assert meta["language"] == ""
        assert meta["inferred_title"] == ""
        assert meta["inferred_authors"] == []
        assert meta["abstract"] == ""
        assert meta["num_sections"] == 1
        assert len(meta["figure_index"]) == 1
        assert meta["figure_index"][0]["caption"] == "Fig 1"
        assert len(meta["table_index"]) == 1
        assert meta["visual_pages"] == [1]

    def test_visual_pages_includes_vector_visual_elements(self):
        from app.processing.metadata import heuristic_build_document_meta

        root = Section(
            id="sec-root", title="(root)", level=0, path="", page_range=[1, 2]
        )
        root.children = [
            Section(
                id="sec-1",
                title="Charts",
                level=1,
                path="Charts",
                page_range=[1, 2],
                elements=[
                    ElementRef(
                        id="el-v",
                        type="image",
                        page=2,
                        text="",
                        extra={"vector_visual": True},
                    )
                ],
            ),
        ]

        meta = heuristic_build_document_meta(
            root, document_id="d2", filename="charts.pdf", num_pages=2
        )

        assert meta["visual_pages"] == [2]


# ---------------------------------------------------------------------------
# Fallback behaviour in get_sections_index / get_document_meta
# ---------------------------------------------------------------------------


def _make_status_ready():
    from app.db.repositories.document_state import DocumentStatus

    return DocumentStatus(
        status="ready", stage="ready", progress=1.0, filename="f.pdf", num_pages=5
    )


def _make_status_processing():
    from app.db.repositories.document_state import DocumentStatus

    return DocumentStatus(
        status="embedding", stage="chunking", progress=0.8, filename="f.pdf"
    )


def _make_tree_data():
    """Minimal tree that can be deserialized and walked."""
    return {
        "document_id": "d1",
        "filename": "f.pdf",
        "num_pages": 3,
        "sections": [
            {
                "id": "sec-1",
                "title": "Intro",
                "level": 1,
                "path": "Intro",
                "page_range": [1, 3],
                "elements": [
                    {
                        "id": "el-1",
                        "type": "text",
                        "page": 1,
                        "text": "This is the first sentence of the intro.",
                    }
                ],
                "children": [],
            }
        ],
    }


class TestFallbackSectionsIndex:
    @pytest.mark.asyncio
    async def test_returns_existing_data_immediately(self, monkeypatch):
        """When enrichment exists, return it without touching the tree."""
        existing = [{"id": "sec-1", "title": "Intro", "summary": "LLM summary"}]

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session

        mock_repo = MagicMock()
        mock_repo.get_sections_index = AsyncMock(return_value=existing)

        monkeypatch.setattr(
            "app.document_data.get_db_session_maker",
            lambda: MagicMock(return_value=mock_session_ctx),
        )
        monkeypatch.setattr(
            "app.document_data.DocumentStateRepository",
            lambda s: mock_repo,
        )

        result = await document_data.get_sections_index("d1")
        assert result == existing
        mock_repo.get_tree.assert_not_called()
        mock_repo.get_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_for_non_ready_document(self, monkeypatch):
        """Do not reconstruct enrichment for documents still processing."""
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session

        mock_repo = MagicMock()
        mock_repo.get_sections_index = AsyncMock(return_value=None)
        mock_repo.get_status = AsyncMock(return_value=_make_status_processing())

        monkeypatch.setattr(
            "app.document_data.get_db_session_maker",
            lambda: MagicMock(return_value=mock_session_ctx),
        )
        monkeypatch.setattr(
            "app.document_data.DocumentStateRepository",
            lambda s: mock_repo,
        )

        result = await document_data.get_sections_index("d1")
        assert result is None
        mock_repo.get_tree.assert_not_called()
        mock_repo.save_sections_index.assert_not_called()

    @pytest.mark.asyncio
    async def test_reconstructs_and_saves_for_ready_document(self, monkeypatch):
        """Ready doc with tree but no enrichment → reconstruct & save back."""
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session

        mock_repo = MagicMock()
        mock_repo.get_sections_index = AsyncMock(return_value=None)
        mock_repo.get_status = AsyncMock(return_value=_make_status_ready())
        mock_repo.get_tree = AsyncMock(return_value=_make_tree_data())
        mock_repo.save_sections_index = AsyncMock()

        monkeypatch.setattr(
            "app.document_data.get_db_session_maker",
            lambda: MagicMock(return_value=mock_session_ctx),
        )
        monkeypatch.setattr(
            "app.document_data.DocumentStateRepository",
            lambda s: mock_repo,
        )

        result = await document_data.get_sections_index("d1")
        assert result is not None
        assert len(result) == 1
        assert result[0]["id"] == "sec-1"
        assert result[0]["title"] == "Intro"

        mock_repo.save_sections_index.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_tree(self, monkeypatch):
        """Ready doc with no tree → give up."""
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session

        mock_repo = MagicMock()
        mock_repo.get_sections_index = AsyncMock(return_value=None)
        mock_repo.get_status = AsyncMock(return_value=_make_status_ready())
        mock_repo.get_tree = AsyncMock(return_value=None)

        monkeypatch.setattr(
            "app.document_data.get_db_session_maker",
            lambda: MagicMock(return_value=mock_session_ctx),
        )
        monkeypatch.setattr(
            "app.document_data.DocumentStateRepository",
            lambda s: mock_repo,
        )

        result = await document_data.get_sections_index("d1")
        assert result is None
        mock_repo.save_sections_index.assert_not_called()

    @pytest.mark.asyncio
    async def test_corrupt_tree_caught_returns_none(self, monkeypatch):
        """Malformed tree (missing required keys) → log & return None."""
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session

        mock_repo = MagicMock()
        mock_repo.get_sections_index = AsyncMock(return_value=None)
        mock_repo.get_status = AsyncMock(return_value=_make_status_ready())
        mock_repo.get_tree = AsyncMock(
            return_value={
                "document_id": "d1",
                "filename": "f.pdf",
                "num_pages": 1,
                "sections": [{"id": "sec-1"}],  # missing required keys
            }
        )

        monkeypatch.setattr(
            "app.document_data.get_db_session_maker",
            lambda: MagicMock(return_value=mock_session_ctx),
        )
        monkeypatch.setattr(
            "app.document_data.DocumentStateRepository",
            lambda s: mock_repo,
        )

        result = await document_data.get_sections_index("d1")
        assert result is None


class TestFallbackDocumentMeta:
    @pytest.mark.asyncio
    async def test_returns_existing_data_immediately(self, monkeypatch):
        existing = {"document_id": "d1", "doc_type": "research_paper"}

        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session

        mock_repo = MagicMock()
        mock_repo.get_document_meta = AsyncMock(return_value=existing)

        monkeypatch.setattr(
            "app.document_data.get_db_session_maker",
            lambda: MagicMock(return_value=mock_session_ctx),
        )
        monkeypatch.setattr(
            "app.document_data.DocumentStateRepository",
            lambda s: mock_repo,
        )

        result = await document_data.get_document_meta("d1")
        assert result == existing
        mock_repo.get_tree.assert_not_called()

    @pytest.mark.asyncio
    async def test_reconstructs_and_saves_for_ready_document(self, monkeypatch):
        mock_session = AsyncMock()
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__.return_value = mock_session

        mock_repo = MagicMock()
        mock_repo.get_document_meta = AsyncMock(return_value=None)
        mock_repo.get_status = AsyncMock(return_value=_make_status_ready())
        mock_repo.get_tree = AsyncMock(return_value=_make_tree_data())
        mock_repo.save_document_meta = AsyncMock()

        monkeypatch.setattr(
            "app.document_data.get_db_session_maker",
            lambda: MagicMock(return_value=mock_session_ctx),
        )
        monkeypatch.setattr(
            "app.document_data.DocumentStateRepository",
            lambda s: mock_repo,
        )

        result = await document_data.get_document_meta("d1")
        assert result is not None
        assert result["document_id"] == "d1"
        assert result["filename"] == "f.pdf"
        assert result["num_sections"] == 1
        assert result["doc_type"] == "other"

        mock_repo.save_document_meta.assert_awaited_once()
        mock_session.commit.assert_awaited_once()
