from __future__ import annotations

from collections import Counter

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_index import DocumentIndex
from app.models.enums import DocumentIndexType


INDEX_TYPES = (DocumentIndexType.VECTOR, DocumentIndexType.GRAPH)


def build_knowledge_base_rag_health(db: Session, *, knowledge_base_id: int) -> dict[str, object]:
    document_status_counts = _count_documents_by_status(db, knowledge_base_id=knowledge_base_id)
    document_count = sum(document_status_counts.values())
    index_status_counts = {
        index_type.value: _count_indexes_by_status(
            db,
            knowledge_base_id=knowledge_base_id,
            index_type=index_type,
            document_count=document_count,
        )
        for index_type in INDEX_TYPES
    }
    return {
        "document_count": document_count,
        "document_status_counts": document_status_counts,
        "index_status_counts": index_status_counts,
    }


def _count_documents_by_status(db: Session, *, knowledge_base_id: int) -> dict[str, int]:
    statement = (
        select(Document.processing_status, func.count(Document.id))
        .where(Document.knowledge_base_id == knowledge_base_id)
        .group_by(Document.processing_status)
    )
    counts = Counter[str]()
    for status, count in db.execute(statement):
        counts[str(status.value if hasattr(status, "value") else status)] = int(count)
    return dict(counts)


def _count_indexes_by_status(
    db: Session,
    *,
    knowledge_base_id: int,
    index_type: DocumentIndexType,
    document_count: int,
) -> dict[str, int]:
    status_statement = (
        select(DocumentIndex.status, func.count(DocumentIndex.id))
        .where(
            DocumentIndex.knowledge_base_id == knowledge_base_id,
            DocumentIndex.index_type == index_type,
        )
        .group_by(DocumentIndex.status)
    )
    counts = Counter[str]()
    indexed_document_ids_statement = select(
        func.count(distinct(DocumentIndex.document_id))
    ).where(
        DocumentIndex.knowledge_base_id == knowledge_base_id,
        DocumentIndex.index_type == index_type,
    )
    for status, count in db.execute(status_statement):
        counts[str(status.value if hasattr(status, "value") else status)] = int(count)

    indexed_document_count = int(db.scalar(indexed_document_ids_statement) or 0)
    counts["missing"] = max(document_count - indexed_document_count, 0)
    return dict(counts)
