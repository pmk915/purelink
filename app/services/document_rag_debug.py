from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document
from app.models.document_block import DocumentBlock
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.document_index import DocumentIndex
from app.models.enums import DocumentIndexType
from app.models.processing_job import ProcessingJob
from app.services.embedding_provider import EmbeddingProviderError
from app.services.indexing.index_metadata_service import (
    check_vector_index_compatibility,
    get_vector_index_identity_from_settings,
)


def build_document_rag_debug(
    db: Session,
    *,
    document: Document,
) -> dict[str, object]:
    vector_index = _get_document_index(
        db,
        document_id=document.id,
        index_type=DocumentIndexType.VECTOR,
    )
    graph_index = _get_document_index(
        db,
        document_id=document.id,
        index_type=DocumentIndexType.GRAPH,
    )
    latest_job = _get_latest_processing_job(db, document_id=document.id)

    return {
        "document_id": document.id,
        "knowledge_base_id": document.knowledge_base_id,
        "processing_status": document.processing_status,
        "chunk_count": _count_rows(db, DocumentChunk, document_id=document.id),
        "citation_unit_count": _count_rows(db, DocumentCitationUnit, document_id=document.id),
        "block_count": _count_rows(db, DocumentBlock, document_id=document.id),
        "vector_index": _serialize_index(vector_index, include_compatibility=True),
        "graph_index": _serialize_index(graph_index, include_compatibility=False),
        "latest_processing_job": _serialize_processing_job(latest_job),
    }


def _count_rows(db: Session, model: type, *, document_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(model.id)).where(model.document_id == document_id)
        )
        or 0
    )


def _get_document_index(
    db: Session,
    *,
    document_id: int,
    index_type: DocumentIndexType,
) -> DocumentIndex | None:
    return db.scalar(
        select(DocumentIndex).where(
            DocumentIndex.document_id == document_id,
            DocumentIndex.index_type == index_type,
        )
    )


def _get_latest_processing_job(
    db: Session,
    *,
    document_id: int,
) -> ProcessingJob | None:
    return db.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.id.desc())
        .limit(1)
    )


def _serialize_index(
    index: DocumentIndex | None,
    *,
    include_compatibility: bool,
) -> dict[str, object] | None:
    if index is None:
        return None

    compatible: bool | None = None
    stale_reason = index.stale_reason
    if include_compatibility:
        try:
            provider, model_name, model_dim, _ = get_vector_index_identity_from_settings(
                get_settings()
            )
            compatible, compatibility_reason = check_vector_index_compatibility(
                index,
                current_provider=provider,
                current_model_name=model_name,
                current_model_dim=model_dim,
            )
            stale_reason = stale_reason or compatibility_reason
        except EmbeddingProviderError as exc:
            compatible = False
            stale_reason = f"embedding_provider_unavailable:{getattr(exc, 'error_code', None) or type(exc).__name__}"

    return {
        "status": index.status,
        "provider": index.provider,
        "model_name": index.model_name,
        "model_dim": index.model_dim,
        "model_version": index.model_version,
        "compatible": compatible,
        "stale_reason": stale_reason,
        "error_message": index.error_message,
    }


def _serialize_processing_job(job: ProcessingJob | None) -> dict[str, object] | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "status": job.status,
        "job_type": job.job_type,
        "step": job.current_step,
        "error_code": job.error_code,
        "error_message": job.error_message,
    }
