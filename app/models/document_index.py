from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DocumentIndexStatus, DocumentIndexType, enum_values
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.knowledge_base import KnowledgeBase


class DocumentIndex(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_indexes"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "index_type",
            name="uq_document_indexes_document_id_index_type",
        ),
        Index("ix_document_indexes_provider_model_name", "provider", "model_name"),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    index_type: Mapped[DocumentIndexType] = mapped_column(
        SAEnum(
            DocumentIndexType,
            name="document_index_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        index=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[DocumentIndexStatus] = mapped_column(
        SAEnum(
            DocumentIndexStatus,
            name="document_index_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=DocumentIndexStatus.PENDING,
        server_default=DocumentIndexStatus.PENDING.value,
        index=True,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stale_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["Document"] = relationship(back_populates="indexes")
    knowledge_base: Mapped["KnowledgeBase"] = relationship()
