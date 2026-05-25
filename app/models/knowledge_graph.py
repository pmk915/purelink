from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.document_citation_unit import DocumentCitationUnit
    from app.models.document_chunk import DocumentChunk
    from app.models.knowledge_base import KnowledgeBase


class KnowledgeEntity(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_entities"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id",
            "normalized_name",
            name="uq_knowledge_entities_knowledge_base_id_normalized_name",
        ),
        Index("ix_knowledge_entities_kb_type", "knowledge_base_id", "entity_type"),
    )

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    knowledge_base: Mapped["KnowledgeBase"] = relationship()
    mentions: Mapped[list["EntityMention"]] = relationship(
        back_populates="entity",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    outgoing_relations: Mapped[list["KnowledgeRelation"]] = relationship(
        back_populates="source_entity",
        cascade="all, delete-orphan",
        foreign_keys="KnowledgeRelation.source_entity_id",
        passive_deletes=True,
    )
    incoming_relations: Mapped[list["KnowledgeRelation"]] = relationship(
        back_populates="target_entity",
        cascade="all, delete-orphan",
        foreign_keys="KnowledgeRelation.target_entity_id",
        passive_deletes=True,
    )


class KnowledgeRelation(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_relations"
    __table_args__ = (
        Index(
            "ix_knowledge_relations_kb_relation_type",
            "knowledge_base_id",
            "relation_type",
        ),
        Index(
            "ix_knowledge_relations_source_target",
            "source_entity_id",
            "target_entity_id",
        ),
    )

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    source_entity_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    target_entity_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    source_chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    source_citation_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_citation_units.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    knowledge_base: Mapped["KnowledgeBase"] = relationship()
    source_entity: Mapped["KnowledgeEntity"] = relationship(
        back_populates="outgoing_relations",
        foreign_keys=[source_entity_id],
    )
    target_entity: Mapped["KnowledgeEntity"] = relationship(
        back_populates="incoming_relations",
        foreign_keys=[target_entity_id],
    )
    source_document: Mapped["Document | None"] = relationship()
    source_chunk: Mapped["DocumentChunk | None"] = relationship()
    source_citation_unit: Mapped["DocumentCitationUnit | None"] = relationship()


class EntityMention(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "entity_mentions"
    __table_args__ = (
        Index("ix_entity_mentions_entity_document", "entity_id", "document_id"),
    )

    entity_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    citation_unit_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_citation_units.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    text_span: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_locator: Mapped[str | None] = mapped_column(String(255), nullable=True)

    entity: Mapped["KnowledgeEntity"] = relationship(back_populates="mentions")
    knowledge_base: Mapped["KnowledgeBase"] = relationship()
    document: Mapped["Document"] = relationship()
    chunk: Mapped["DocumentChunk | None"] = relationship()
    citation_unit: Mapped["DocumentCitationUnit | None"] = relationship()
