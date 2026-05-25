from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DocumentBlockType, enum_values
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document


class DocumentBlock(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_blocks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "order_index",
            name="uq_document_blocks_document_id_order_index",
        ),
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    block_type: Mapped[DocumentBlockType] = mapped_column(
        SAEnum(
            DocumentBlockType,
            name="document_block_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        index=True,
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_locator: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    heading_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="blocks")
