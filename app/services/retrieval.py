from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.models.document import Document
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.services.document_embedding import RetrievedChunk, search_index


def retrieve_chunks_for_documents(
    *,
    documents: Sequence[Document],
    vector_root: Path,
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    query: str,
    top_k: int,
    required_review_status: DocumentReviewStatus,
    team_id: int | None = None,
) -> list[RetrievedChunk]:
    allowed_document_ids = {
        item.id
        for item in documents
        if item.review_status == required_review_status
        and item.processing_status == DocumentProcessingStatus.INDEXED
    }
    return search_index(
        vector_root=vector_root,
        scope=scope,
        knowledge_base_id=knowledge_base_id,
        query=query,
        top_k=top_k,
        team_id=team_id,
        allowed_document_ids=allowed_document_ids,
    )
