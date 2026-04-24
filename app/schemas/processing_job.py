from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    DocumentProcessingStatus,
    ProcessingJobStatus,
    ProcessingJobTrigger,
    ProcessingJobType,
)


class ProcessingJobSubmissionRead(BaseModel):
    document_id: int
    document_status: DocumentProcessingStatus
    job_id: int
    job_type: ProcessingJobType
    job_status: ProcessingJobStatus
    trigger_type: ProcessingJobTrigger
    attempt_number: int


class ProcessingJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    triggered_by_id: int
    previous_job_id: int | None
    job_type: ProcessingJobType
    trigger_type: ProcessingJobTrigger
    status: ProcessingJobStatus
    current_step: str | None
    attempt_number: int
    worker_name: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
