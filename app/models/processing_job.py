from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    ProcessingJobStatus,
    ProcessingJobTrigger,
    ProcessingJobType,
    enum_values,
)
from app.models.mixins import PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.user import User


class ProcessingJob(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "processing_jobs"

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    triggered_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    previous_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    job_type: Mapped[ProcessingJobType] = mapped_column(
        SAEnum(
            ProcessingJobType,
            name="processing_job_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=ProcessingJobType.DOCUMENT_PROCESS,
        server_default=ProcessingJobType.DOCUMENT_PROCESS.value,
        nullable=False,
    )
    trigger_type: Mapped[ProcessingJobTrigger] = mapped_column(
        SAEnum(
            ProcessingJobTrigger,
            name="processing_job_trigger",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=ProcessingJobTrigger.PROCESS,
        server_default=ProcessingJobTrigger.PROCESS.value,
        nullable=False,
    )
    status: Mapped[ProcessingJobStatus] = mapped_column(
        SAEnum(
            ProcessingJobStatus,
            name="processing_job_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=enum_values,
        ),
        default=ProcessingJobStatus.QUEUED,
        server_default=ProcessingJobStatus.QUEUED.value,
        nullable=False,
    )
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )
    worker_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["Document"] = relationship(back_populates="processing_jobs")
    triggered_by_user: Mapped["User"] = relationship(
        back_populates="triggered_processing_jobs",
        foreign_keys=[triggered_by_id],
    )
    previous_job: Mapped["ProcessingJob | None"] = relationship(
        remote_side="ProcessingJob.id",
        foreign_keys=[previous_job_id],
    )
