from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RetrievalFilteredReason, enum_values
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.document_citation_unit import DocumentCitationUnit
    from app.models.document_chunk import DocumentChunk
    from app.models.knowledge_base import KnowledgeBase
    from app.models.user import User


class RetrievalTrace(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "retrieval_traces"

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    knowledge_base_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    query: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    top_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initial_candidate_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    final_evidence_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    reranker_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    used_reranker: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    reranker_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reranker_model: Mapped[str | None] = mapped_column(String(255), nullable=True)

    embedding_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User | None"] = relationship()
    knowledge_base: Mapped["KnowledgeBase | None"] = relationship()
    items: Mapped[list["RetrievalTraceItem"]] = relationship(
        back_populates="trace",
        cascade="all, delete-orphan",
        order_by="RetrievalTraceItem.id",
    )


class RetrievalTraceItem(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "retrieval_trace_items"
    __table_args__ = (
        Index("ix_retrieval_trace_items_trace_final_rank", "trace_id", "final_rank"),
    )

    trace_id: Mapped[int] = mapped_column(
        ForeignKey("retrieval_traces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
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

    document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_locator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_text_preview: Mapped[str | None] = mapped_column(Text, nullable=True)

    vector_score: Mapped[float | None] = mapped_column(nullable=True)
    keyword_score: Mapped[float | None] = mapped_column(nullable=True)
    graph_score: Mapped[float | None] = mapped_column(nullable=True)
    rerank_score: Mapped[float | None] = mapped_column(nullable=True)
    final_score: Mapped[float | None] = mapped_column(nullable=True)

    initial_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rerank_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    selected_for_context: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True, nullable=False)
    filtered_reason: Mapped[RetrievalFilteredReason] = mapped_column(
        SAEnum(
            RetrievalFilteredReason,
            name="retrieval_filtered_reason",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=RetrievalFilteredReason.UNKNOWN,
        server_default=RetrievalFilteredReason.UNKNOWN.value,
        index=True,
        nullable=False,
    )

    index_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    index_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    index_model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    index_model_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    trace: Mapped["RetrievalTrace"] = relationship(back_populates="items")
    document: Mapped["Document | None"] = relationship()
    chunk: Mapped["DocumentChunk | None"] = relationship()
    citation_unit: Mapped["DocumentCitationUnit | None"] = relationship()
