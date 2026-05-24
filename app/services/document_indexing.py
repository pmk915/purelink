from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import (
    DocumentProcessingStatus,
    KnowledgeBaseScope,
)
from app.services.document import update_document_processing_status
from app.services.document_chunker import resolve_chunks_root
from app.services.document_embedding import (
    KB_REINDEX_REQUIRED_ERROR_CODE,
    DocumentEmbeddingError,
    EmbeddedDocumentResult,
    delete_knowledge_base_index_artifact,
    embed_document_chunks,
    embed_ready_document_chunks,
    resolve_vector_store_root,
)
from app.services.indexing.index_metadata_service import (
    get_vector_index_identity_from_settings,
    mark_vector_failed,
    mark_vector_indexed,
    mark_vector_indexing,
)
from app.services.knowledge_graph.graph_index_service import build_document_graph_index
from app.services.processing_job import (
    INDEXING_STEP_BUILD_EMBEDDINGS,
    INDEXING_STEP_FINALIZE_INDEX,
    INDEXING_STEP_LOAD_CHUNKS,
    INDEXING_STEP_WRITE_INDEX,
)

logger = logging.getLogger("purelink.documents")


class DocumentIndexingError(ValueError):
    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


def build_document_index(
    db: Session,
    *,
    document: Document,
    chunks_root: Path,
    vector_root: Path,
    progress_callback: Callable[[str], None] | None = None,
) -> EmbeddedDocumentResult:
    if document.knowledge_base is None:
        raise DocumentIndexingError("Document knowledge base is not available.")
    if document.processing_status not in {
        DocumentProcessingStatus.READY,
        DocumentProcessingStatus.INDEXED,
        DocumentProcessingStatus.PARSED,
    }:
        raise DocumentIndexingError("Document must be ready or chunked before indexing.")

    scope = document.knowledge_base.scope
    team_id = document.knowledge_base.team_id if scope == KnowledgeBaseScope.TEAM else None
    provider_name, model_name, model_dim, model_version = get_vector_index_identity_from_settings(
        get_settings()
    )

    _report(progress_callback, INDEXING_STEP_LOAD_CHUNKS)
    has_database_chunks = _document_has_database_chunks(db, document_id=document.id)

    try:
        mark_vector_indexing(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider=provider_name,
            model_name=model_name,
            model_dim=model_dim,
            model_version=model_version,
        )
        _report(progress_callback, INDEXING_STEP_BUILD_EMBEDDINGS)
        if has_database_chunks:
            try:
                embedded_result = embed_ready_document_chunks(
                    db,
                    document=document,
                    vector_root=vector_root,
                    scope=scope,
                    team_id=team_id,
                )
            except DocumentEmbeddingError as exc:
                if getattr(exc, "error_code", None) != KB_REINDEX_REQUIRED_ERROR_CODE:
                    raise
                embedded_result = _rebuild_knowledge_base_index_from_database_chunks(
                    db,
                    document=document,
                    vector_root=vector_root,
                    scope=scope,
                    team_id=team_id,
                )
        else:
            embedded_result = embed_document_chunks(
                document=document,
                chunks_root=chunks_root,
                vector_root=vector_root,
                scope=scope,
                team_id=team_id,
            )
    except DocumentEmbeddingError as exc:
        mark_vector_failed(
            db,
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            provider=provider_name,
            model_name=model_name,
            model_dim=model_dim,
            model_version=model_version,
            error_message=str(exc),
        )
        raise DocumentIndexingError(str(exc), error_code=getattr(exc, "error_code", None)) from exc

    _report(progress_callback, INDEXING_STEP_WRITE_INDEX)
    mark_vector_indexed(
        db,
        document_id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        provider=embedded_result.embedding_provider,
        model_name=embedded_result.embedding_model,
        model_dim=embedded_result.embedding_dimension,
        model_version=embedded_result.embedding_version,
        indexed_at=embedded_result.indexed_at,
    )
    build_document_graph_index(db, document=document)
    _report(progress_callback, INDEXING_STEP_FINALIZE_INDEX)
    update_document_processing_status(
        db,
        document=document,
        processing_status=DocumentProcessingStatus.INDEXED,
        error_message=None,
        processed_at=datetime.now(UTC),
    )
    return embedded_result


def resolve_indexing_roots(
    *,
    chunks_dir: str | Path,
    vector_store_dir: str | Path,
    base_dir: Path,
) -> tuple[Path, Path]:
    return (
        resolve_chunks_root(chunks_dir, base_dir=base_dir),
        resolve_vector_store_root(vector_store_dir, base_dir=base_dir),
    )


def _document_has_database_chunks(db: Session, *, document_id: int) -> bool:
    statement = select(DocumentChunk.id).where(DocumentChunk.document_id == document_id).limit(1)
    return db.scalar(statement) is not None


def _rebuild_knowledge_base_index_from_database_chunks(
    db: Session,
    *,
    document: Document,
    vector_root: Path,
    scope: KnowledgeBaseScope,
    team_id: int | None,
) -> EmbeddedDocumentResult:
    eligible_documents = list(
        db.scalars(
            select(Document)
            .where(
                Document.knowledge_base_id == document.knowledge_base_id,
                Document.processing_status.in_(
                    (
                        DocumentProcessingStatus.READY,
                        DocumentProcessingStatus.INDEXED,
                        DocumentProcessingStatus.PARSED,
                    )
                ),
            )
            .order_by(Document.id.asc())
        )
    )
    if not eligible_documents:
        raise DocumentIndexingError("Knowledge base does not contain any reindexable documents.")

    delete_knowledge_base_index_artifact(
        vector_root=vector_root,
        scope=scope,
        knowledge_base_id=document.knowledge_base_id,
        team_id=team_id,
    )

    rebuilt_count = 0
    target_result: EmbeddedDocumentResult | None = None
    rebuild_started_at = datetime.now(UTC)
    for candidate in eligible_documents:
        if not _document_has_database_chunks(db, document_id=candidate.id):
            continue
        provider_name, model_name, model_dim, model_version = get_vector_index_identity_from_settings(
            get_settings()
        )
        mark_vector_indexing(
            db,
            document_id=candidate.id,
            knowledge_base_id=candidate.knowledge_base_id,
            provider=provider_name,
            model_name=model_name,
            model_dim=model_dim,
            model_version=model_version,
        )
        embedded_result = embed_ready_document_chunks(
            db,
            document=candidate,
            vector_root=vector_root,
            scope=scope,
            team_id=team_id,
        )
        mark_vector_indexed(
            db,
            document_id=candidate.id,
            knowledge_base_id=candidate.knowledge_base_id,
            provider=embedded_result.embedding_provider,
            model_name=embedded_result.embedding_model,
            model_dim=embedded_result.embedding_dimension,
            model_version=embedded_result.embedding_version,
            indexed_at=embedded_result.indexed_at,
        )
        update_document_processing_status(
            db,
            document=candidate,
            processing_status=DocumentProcessingStatus.INDEXED,
            error_message=None,
            processed_at=rebuild_started_at,
        )
        rebuilt_count += 1
        if candidate.id == document.id:
            target_result = embedded_result

    logger.info(
        "knowledge base index rebuilt from database chunks knowledge_base_id=%s scope=%s team_id=%s rebuilt_document_count=%s target_document_id=%s",
        document.knowledge_base_id,
        scope.value,
        team_id,
        rebuilt_count,
        document.id,
    )

    if target_result is None:
        raise DocumentIndexingError("Document chunk records do not exist.")
    return target_result


def _report(callback: Callable[[str], None] | None, step: str) -> None:
    if callback is not None:
        callback(step)
