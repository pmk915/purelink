from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentTaskStatus, DocumentTaskType


class DocumentTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    task_type: DocumentTaskType
    status: DocumentTaskStatus
    error_message: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
