from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR, get_settings
from app.models.document import Document
from app.models.document_block import DocumentBlock
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.document_chunk import DocumentChunk
from app.models.document_index import DocumentIndex
from app.models.enums import (
    DocumentIndexStatus,
    DocumentIndexType,
    DocumentProcessingStatus,
)
from app.models.knowledge_graph import EntityMention, KnowledgeRelation
from app.models.processing_job import ProcessingJob
from app.services.document import resolve_upload_root
from app.services.embedding_provider import EmbeddingProviderError
from app.services.indexing.index_metadata_service import (
    check_vector_index_compatibility,
    get_vector_index_identity_from_settings,
)


READY = "ready"
MISSING = "missing"
WARNING = "warning"
FAILED = "failed"
PENDING = "pending"
OPTIONAL = "optional"


def build_document_status(db: Session, *, document: Document) -> dict[str, Any]:
    block_count = _count_rows(db, DocumentBlock, document_id=document.id)
    chunk_count = _count_rows(db, DocumentChunk, document_id=document.id)
    citation_unit_count = _count_rows(db, DocumentCitationUnit, document_id=document.id)
    entity_count = _count_distinct_entity_mentions(db, document_id=document.id)
    relation_count = _count_relations(db, document_id=document.id)
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
    settings = get_settings()
    upload_root = resolve_upload_root(settings.upload_dir, base_dir=BASE_DIR)
    latest_job_can_retry = (
        _can_retry_latest_job(db, latest_job=latest_job, upload_root=upload_root)
        if latest_job is not None
        else False
    )
    vector_index_status, vector_compatible, vector_warning = _resolve_vector_index_status(vector_index)
    graph_index_status = _resolve_graph_index_status(graph_index)
    vector_index_count = chunk_count if vector_index_status == READY else 0
    error_code = latest_job.error_code if latest_job is not None else None
    error_message = _first_present(
        document.error_message,
        latest_job.error_message if latest_job is not None else None,
        vector_index.error_message if vector_index is not None else None,
    )

    checks = [
        _build_check(
            name="processing",
            label="Processing",
            status=_processing_check_status(document.processing_status, error_message),
            count=None,
            message=_processing_message(document.processing_status, latest_job),
        ),
        _build_check(
            name="document_blocks",
            label="Document blocks",
            status=READY if block_count > 0 else WARNING,
            count=block_count,
            message=(
                f"{block_count} blocks available"
                if block_count > 0
                else "No document blocks found; legacy documents may need reprocessing"
            ),
        ),
        _build_check(
            name="chunks",
            label="Chunks",
            status=READY if chunk_count > 0 else MISSING,
            count=chunk_count,
            message=(
                f"{chunk_count} chunks available"
                if chunk_count > 0
                else "No chunks found"
            ),
        ),
        _build_check(
            name="citation_units",
            label="Citation units",
            status=READY if citation_unit_count > 0 else MISSING,
            count=citation_unit_count,
            message=(
                f"{citation_unit_count} citation units available"
                if citation_unit_count > 0
                else "No citation units found"
            ),
        ),
        _build_check(
            name="vector_index",
            label="Vector index",
            status=vector_index_status,
            count=vector_index_count,
            message=_index_message("Vector index", vector_index_status, vector_index_count, vector_warning),
        ),
        _build_check(
            name="graph_index",
            label="Graph index",
            status=graph_index_status if graph_index_status != MISSING else OPTIONAL,
            count=relation_count,
            message=_graph_message(graph_index_status, entity_count, relation_count),
        ),
    ]
    warnings = [
        check["message"]
        for check in checks
        if check["status"] in {WARNING, OPTIONAL}
    ]
    if vector_warning:
        warnings.append(vector_warning)

    rag_ready = (
        document.processing_status != DocumentProcessingStatus.FAILED
        and chunk_count > 0
        and citation_unit_count > 0
        and vector_index_status == READY
        and vector_index_count > 0
        and not error_message
    )

    last_indexed_at = _latest_datetime(
        vector_index.indexed_at if vector_index is not None else None,
        graph_index.indexed_at if graph_index is not None else None,
    )

    return {
        "document_id": document.id,
        "kb_id": document.knowledge_base_id,
        "filename": document.original_filename,
        "processing_status": document.processing_status,
        "rag_ready": rag_ready,
        "block_count": block_count,
        "chunk_count": chunk_count,
        "citation_unit_count": citation_unit_count,
        "vector_index_status": vector_index_status,
        "vector_index_count": vector_index_count,
        "vector_index_compatible": vector_compatible,
        "graph_index_status": graph_index_status,
        "entity_count": entity_count,
        "relation_count": relation_count,
        "latest_processing_job_step": latest_job.current_step if latest_job is not None else None,
        "latest_processing_job_status": latest_job.status if latest_job is not None else None,
        "latest_processing_job_id": latest_job.id if latest_job is not None else None,
        "latest_processing_job_attempt_count": latest_job.attempt_number if latest_job is not None else None,
        "latest_processing_job_max_attempts": (
            latest_job.max_retries + 1 if latest_job is not None else None
        ),
        "latest_processing_job_can_retry": latest_job_can_retry,
        "latest_processing_job_error_code": latest_job.error_code if latest_job is not None else None,
        "latest_processing_job_error_message": (
            latest_job.error_message if latest_job is not None else None
        ),
        "error_code": error_code,
        "error_message": error_message,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "last_indexed_at": last_indexed_at,
        "warnings": warnings,
        "checks": checks,
    }


def _count_rows(db: Session, model: type, *, document_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(model.id)).where(model.document_id == document_id)
        )
        or 0
    )


def _count_distinct_entity_mentions(db: Session, *, document_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(func.distinct(EntityMention.entity_id))).where(
                EntityMention.document_id == document_id
            )
        )
        or 0
    )


def _count_relations(db: Session, *, document_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(KnowledgeRelation.id)).where(
                KnowledgeRelation.source_document_id == document_id
            )
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


def _can_retry_latest_job(
    db: Session,
    *,
    latest_job: ProcessingJob,
    upload_root,
) -> bool:
    from app.services.processing_job import can_retry_document_processing_job

    return can_retry_document_processing_job(
        db,
        job=latest_job,
        upload_root=upload_root,
    )


def _resolve_vector_index_status(index: DocumentIndex | None) -> tuple[str, bool | None, str | None]:
    if index is None:
        return MISSING, None, None
    if index.status == DocumentIndexStatus.FAILED:
        return FAILED, False, index.error_message
    if index.status == DocumentIndexStatus.STALE:
        return WARNING, False, index.stale_reason
    if index.status in {DocumentIndexStatus.PENDING, DocumentIndexStatus.INDEXING}:
        return PENDING, False, None

    compatible = None
    warning = index.stale_reason
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
        warning = warning or compatibility_reason
    except EmbeddingProviderError as exc:
        return FAILED, False, f"embedding_provider_unavailable:{getattr(exc, 'error_code', None) or type(exc).__name__}"

    if compatible is False:
        return WARNING, compatible, warning
    return READY, compatible, warning


def _resolve_graph_index_status(index: DocumentIndex | None) -> str:
    if index is None:
        return MISSING
    if index.status == DocumentIndexStatus.INDEXED:
        return READY
    if index.status == DocumentIndexStatus.FAILED:
        return WARNING
    if index.status == DocumentIndexStatus.STALE:
        return WARNING
    return PENDING


def _processing_check_status(
    processing_status: DocumentProcessingStatus,
    error_message: str | None,
) -> str:
    if processing_status == DocumentProcessingStatus.FAILED or error_message:
        return FAILED
    if processing_status in {DocumentProcessingStatus.INDEXED, DocumentProcessingStatus.READY}:
        return READY
    if processing_status == DocumentProcessingStatus.PROCESSING:
        return PENDING
    return WARNING


def _processing_message(
    processing_status: DocumentProcessingStatus,
    latest_job: ProcessingJob | None,
) -> str:
    if latest_job is not None and latest_job.current_step:
        return f"Latest job step: {latest_job.current_step}"
    return f"Processing status: {processing_status.value}"


def _index_message(
    label: str,
    status: str,
    count: int,
    warning: str | None,
) -> str:
    if status == READY:
        return f"{label} ready with {count} chunks"
    if warning:
        return warning
    if status == MISSING:
        return f"{label} is missing"
    return f"{label} status is {status}"


def _graph_message(status: str, entity_count: int, relation_count: int) -> str:
    if status == READY:
        return f"Graph ready with {entity_count} entities and {relation_count} relations"
    if status == MISSING:
        return "Graph index is optional and not built yet"
    return f"Graph index status is {status}"


def _build_check(
    *,
    name: str,
    label: str,
    status: str,
    count: int | None,
    message: str,
) -> dict[str, object]:
    return {
        "name": name,
        "label": label,
        "status": status,
        "count": count,
        "message": message,
    }


def _first_present(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _latest_datetime(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None
