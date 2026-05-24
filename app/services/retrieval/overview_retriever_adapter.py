from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.document import Document
from app.models.enums import DocumentReviewStatus, KnowledgeBaseScope
from app.services.document_embedding import RetrievedChunk
from app.services.overview_retrieval import collect_overview_chunks


def retrieve_overview_chunks(
    *,
    db: Session,
    documents: Sequence[Document],
    knowledge_base_id: int,
    scope: KnowledgeBaseScope,
    required_review_status: DocumentReviewStatus,
    team_id: int | None,
    settings: Settings,
) -> list[RetrievedChunk]:
    return collect_overview_chunks(
        db=db,
        documents=documents,
        knowledge_base_id=knowledge_base_id,
        scope=scope,
        required_review_status=required_review_status,
        team_id=team_id,
        max_chunks=settings.overview_max_chunks,
        max_chunks_per_document=settings.overview_max_chunks_per_document,
    )
