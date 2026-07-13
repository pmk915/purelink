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
    query: str | None = None,
    target_document_ids: Sequence[int] | None = None,
    overview_scope: str = "knowledge_base",
    target_document_requested: bool = False,
) -> list[RetrievedChunk]:
    return collect_overview_chunks(
        db=db,
        documents=documents,
        knowledge_base_id=knowledge_base_id,
        scope=scope,
        required_review_status=required_review_status,
        team_id=team_id,
        query=query,
        target_document_ids=target_document_ids,
        overview_scope=overview_scope,
        target_document_requested=target_document_requested,
        max_chunks=settings.overview_max_chunks,
        max_chunks_per_document=settings.overview_max_chunks_per_document,
    )
