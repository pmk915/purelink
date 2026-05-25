from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.document_chunk import DocumentChunk


class DocumentCitationUnit(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_citation_units"
    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "unit_index",
            name="uq_document_citation_units_chunk_id_unit_index",
        ),
        UniqueConstraint(
            "document_id",
            "unit_index",
            name="uq_document_citation_units_document_id_unit_index",
        ),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_key: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    unit_index: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_text: Mapped[str] = mapped_column(Text, nullable=False)
    start_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_char: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="citation_units")
    chunk: Mapped["DocumentChunk"] = relationship(back_populates="citation_units")
