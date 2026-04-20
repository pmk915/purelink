from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import BASE_DIR, get_settings
from app.models.document import Document
from app.models.document_task import DocumentTask
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    DocumentTaskStatus,
    DocumentTaskType,
    KnowledgeBaseScope,
)
from app.services.document_chunker import build_chunk_relative_path, resolve_chunks_root
from app.services.document_parser import build_parsed_relative_path, resolve_parsed_root


ACTIVE_DOCUMENT_TASK_STATUSES = (
    DocumentTaskStatus.PENDING,
    DocumentTaskStatus.PROCESSING,
)


class ActiveDocumentTaskExistsError(ValueError):
    pass


class DocumentTaskEligibilityError(ValueError):
    pass


def create_document_task(
    db: Session,
    *,
    document_id: int,
    task_type: DocumentTaskType,
) -> DocumentTask:
    active_task = get_active_document_task(
        db,
        document_id=document_id,
        task_type=task_type,
    )
    if active_task is not None:
        raise ActiveDocumentTaskExistsError(
            f"An active {task_type.value} task already exists for this document.",
        )

    task = DocumentTask(
        document_id=document_id,
        task_type=task_type,
        status=DocumentTaskStatus.PENDING,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_document_task(
    db: Session,
    *,
    task_id: int,
) -> DocumentTask | None:
    statement = (
        select(DocumentTask)
        .options(
            selectinload(DocumentTask.document).selectinload(Document.knowledge_base),
        )
        .where(DocumentTask.id == task_id)
    )
    return db.scalar(statement)


def get_active_document_task(
    db: Session,
    *,
    document_id: int,
    task_type: DocumentTaskType,
) -> DocumentTask | None:
    statement = (
        select(DocumentTask)
        .where(
            DocumentTask.document_id == document_id,
            DocumentTask.task_type == task_type,
            DocumentTask.status.in_(ACTIVE_DOCUMENT_TASK_STATUSES),
        )
        .order_by(DocumentTask.id.desc())
    )
    return db.scalar(statement)


def create_document_task_for_document(
    db: Session,
    *,
    document: Document,
    task_type: DocumentTaskType,
    scope: KnowledgeBaseScope,
    team_id: int | None = None,
) -> DocumentTask:
    ensure_document_is_eligible_for_task(
        document=document,
        task_type=task_type,
        scope=scope,
        team_id=team_id,
    )
    return create_document_task(
        db,
        document_id=document.id,
        task_type=task_type,
    )


def ensure_document_is_eligible_for_task(
    *,
    document: Document,
    task_type: DocumentTaskType,
    scope: KnowledgeBaseScope,
    team_id: int | None = None,
) -> None:
    required_review_status = (
        DocumentReviewStatus.NOT_REQUIRED
        if scope == KnowledgeBaseScope.PERSONAL
        else DocumentReviewStatus.APPROVED
    )
    if document.review_status != required_review_status:
        raise DocumentTaskEligibilityError(
            f"Document is not eligible for {task_type.value} tasks.",
        )

    if task_type == DocumentTaskType.PARSE:
        return

    settings = get_settings()

    if task_type == DocumentTaskType.CHUNK:
        if document.processing_status != DocumentProcessingStatus.PARSED:
            raise DocumentTaskEligibilityError(
                "Document must be parsed before creating a chunk task.",
            )
        parsed_root = resolve_parsed_root(settings.parsed_dir, base_dir=BASE_DIR)
        parsed_path = parsed_root / build_parsed_relative_path(
            scope=scope,
            knowledge_base_id=document.knowledge_base_id,
            document_id=document.id,
            team_id=team_id,
        )
        _ensure_path_exists(
            parsed_path,
            "Parsed document result does not exist.",
        )
        return

    if task_type in {DocumentTaskType.EMBED, DocumentTaskType.INDEX}:
        if document.processing_status not in {
            DocumentProcessingStatus.PARSED,
            DocumentProcessingStatus.INDEXED,
        }:
            raise DocumentTaskEligibilityError(
                f"Document must be chunked before creating an {task_type.value} task.",
            )
        chunks_root = resolve_chunks_root(settings.chunks_dir, base_dir=BASE_DIR)
        chunk_path = chunks_root / build_chunk_relative_path(
            scope=scope,
            knowledge_base_id=document.knowledge_base_id,
            document_id=document.id,
            team_id=team_id,
        )
        _ensure_path_exists(
            chunk_path,
            "Document chunk result does not exist.",
        )
        return

    raise DocumentTaskEligibilityError(
        f"Unsupported document task type: {task_type.value}.",
    )


def _ensure_path_exists(path: Path, error_message: str) -> None:
    if not path.exists():
        raise DocumentTaskEligibilityError(error_message)
