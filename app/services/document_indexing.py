from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.enums import (
    DocumentProcessingStatus,
    KnowledgeBaseScope,
)
from app.services.document import update_document_processing_status
from app.services.document_chunker import resolve_chunks_root
from app.services.document_embedding import (
    DocumentEmbeddingError,
    EmbeddedDocumentResult,
    embed_document_chunks,
    embed_ready_document_chunks,
    resolve_vector_store_root,
)
from app.services.processing_job import (
    INDEXING_STEP_BUILD_EMBEDDINGS,
    INDEXING_STEP_FINALIZE_INDEX,
    INDEXING_STEP_LOAD_CHUNKS,
    INDEXING_STEP_WRITE_INDEX,
)


class DocumentIndexingError(ValueError):
    pass


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

    _report(progress_callback, INDEXING_STEP_LOAD_CHUNKS)
    has_database_chunks = _document_has_database_chunks(db, document_id=document.id)

    try:
        _report(progress_callback, INDEXING_STEP_BUILD_EMBEDDINGS)
        if has_database_chunks:
            embedded_result = embed_ready_document_chunks(
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
        raise DocumentIndexingError(str(exc)) from exc

    _report(progress_callback, INDEXING_STEP_WRITE_INDEX)
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


def _report(callback: Callable[[str], None] | None, step: str) -> None:
    if callback is not None:
        callback(step)
