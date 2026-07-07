"""SQLAlchemy model for the document_chunks table."""

from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, ForeignKey, Integer, String, Text

from app.db.base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    chunk_id = Column(Text, primary_key=True)
    document_id = Column(
        String(64),
        ForeignKey("document_state.document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding = Column(Vector(768), nullable=False)
    type = Column(Text, nullable=False)
    section_path = Column(Text, nullable=False, default="(root)")
    page = Column(Integer, nullable=False, default=1)
    display_text = Column(Text, nullable=False, default="")
    element_ids = Column(JSON, nullable=False, default=list)
    bbox = Column(JSON, nullable=True)
    page_size = Column(JSON, nullable=True)
    extra = Column(JSON, nullable=False, default=dict)
