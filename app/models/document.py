from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import DocumentProcessingStatus, DocumentReviewStatus, enum_values
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.document_citation_unit import DocumentCitationUnit
    from app.models.document_chunk import DocumentChunk
    from app.models.document_task import DocumentTask
    from app.models.knowledge_base import KnowledgeBase
    from app.models.processing_job import ProcessingJob
    from app.models.user import User


class Document(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id",
            "sha256",
            name="uq_documents_knowledge_base_sha256",
        ),
    )

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    submitted_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    review_status: Mapped[DocumentReviewStatus] = mapped_column(
        SAEnum(
            DocumentReviewStatus,
            name="document_review_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=DocumentReviewStatus.NOT_REQUIRED,
        server_default=DocumentReviewStatus.NOT_REQUIRED.value,
        nullable=False,
    )
    processing_status: Mapped[DocumentProcessingStatus] = mapped_column(
        SAEnum(
            DocumentProcessingStatus,
            name="document_processing_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=DocumentProcessingStatus.UPLOADED,
        server_default=DocumentProcessingStatus.UPLOADED.value,
        nullable=False,
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")
    owner: Mapped["User"] = relationship(
        back_populates="documents",
        foreign_keys=[owner_id],
    )
    submitted_by_user: Mapped["User"] = relationship(
        back_populates="submitted_documents",
        foreign_keys=[submitted_by],
    )
    reviewed_by_user: Mapped["User | None"] = relationship(
        back_populates="reviewed_documents",
        foreign_keys=[reviewed_by],
    )
    tasks: Mapped[list["DocumentTask"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )
    citation_units: Mapped[list["DocumentCitationUnit"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentCitationUnit.unit_index",
    )
    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    @property
    def latest_processing_job(self) -> "ProcessingJob | None":
        if not self.processing_jobs:
            return None
        return max(self.processing_jobs, key=lambda job: job.id)

    @property
    def latest_processing_job_id(self) -> int | None:
        latest_job = self.latest_processing_job
        if latest_job is None:
            return None
        return latest_job.id

    @property
    def latest_processing_job_status(self):
        latest_job = self.latest_processing_job
        if latest_job is None:
            return None
        return latest_job.status

    @property
    def latest_processing_job_type(self):
        latest_job = self.latest_processing_job
        if latest_job is None:
            return None
        return latest_job.job_type

    @property
    def latest_processing_job_step(self) -> str | None:
        latest_job = self.latest_processing_job
        if latest_job is None:
            return None
        return latest_job.current_step

    @property
    def latest_processing_job_error_code(self) -> str | None:
        latest_job = self.latest_processing_job
        if latest_job is None:
            return None
        return latest_job.error_code

    @property
    def latest_processing_job_last_error(self) -> str | None:
        latest_job = self.latest_processing_job
        if latest_job is None:
            return None
        return latest_job.last_error

    @property
    def latest_processing_job_trigger(self):
        latest_job = self.latest_processing_job
        if latest_job is None:
            return None
        return latest_job.trigger_type

    @property
    def latest_processing_job_attempt_number(self) -> int | None:
        latest_job = self.latest_processing_job
        if latest_job is None:
            return None
        return latest_job.attempt_number
