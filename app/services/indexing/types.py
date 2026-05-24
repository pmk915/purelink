from __future__ import annotations

from pydantic import BaseModel

from app.models.enums import DocumentIndexStatus as IndexStatus
from app.models.enums import DocumentIndexType as IndexType


class IndexMetadata(BaseModel):
    document_id: int
    knowledge_base_id: int | None = None
    index_type: IndexType
    provider: str
    model_name: str
    model_dim: int | None = None
    model_version: str | None = None
    status: IndexStatus
    error_message: str | None = None
    stale_reason: str | None = None
