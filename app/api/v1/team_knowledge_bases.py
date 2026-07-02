from __future__ import annotations

from datetime import UTC, datetime
import logging
import time

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DBSession
from app.core.config import BASE_DIR, get_settings
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    DocumentTaskType,
    KnowledgeBaseScope,
    ProcessingJobStatus,
    ProcessingJobTrigger,
    ProcessingJobType,
    TeamMemberRole,
)
from app.schemas.document import (
    DocumentChunkRead,
    DocumentParseRead,
    DocumentPreviewRead,
    DocumentRagDebugRead,
    DocumentRead,
    DocumentStatusRead,
    RetrievalQueryRequest,
    RetrievalResponse,
    RetrievedChunkRead,
)
from app.schemas.qa import QuestionAnswerRequest, QuestionAnswerResponse
from app.schemas.document_task import DocumentTaskRead
from app.schemas.processing_job import (
    ProcessingJobListRead,
    ProcessingJobRead,
    ProcessingJobSubmissionRead,
    ProcessingJobSummaryRead,
)
from app.schemas.knowledge_base import (
    KnowledgeBaseRagHealthRead,
    KnowledgeBaseRead,
    KnowledgeBaseReindexRead,
    TeamKnowledgeBaseCreateRequest,
    TeamKnowledgeBaseUpdateRequest,
)
from app.schemas.knowledge_graph import (
    KnowledgeGraphCleanupRead,
    KnowledgeGraphDeduplicationRead,
    KnowledgeGraphEntityDetailRead,
    KnowledgeGraphEntityListRead,
    KnowledgeGraphExportRead,
    KnowledgeGraphDocumentRebuildRead,
)
from app.services.document import (
    compute_document_sha256,
    create_document,
    delete_document_and_artifacts,
    get_document_by_sha256_for_knowledge_base,
    get_document_for_knowledge_base,
    list_documents_for_knowledge_base,
    resolve_upload_root,
    store_document_file,
    update_document_processing_status,
)
from app.services.document_chunker import (
    DocumentChunkError,
    chunk_document_from_parsed_result,
    resolve_chunks_root,
)
from app.services.document_embedding import (
    delete_document_from_knowledge_base_index,
    DocumentEmbeddingError,
    delete_knowledge_base_index_artifact,
    resolve_vector_store_root,
)
from app.services.document_preview import (
    build_document_preview,
    resolve_document_file_path,
)
from app.services.document_rag_debug import build_document_rag_debug
from app.services.document_status import build_document_status
from app.services.document_parser import (
    DocumentParseError,
    parse_document_to_local_result,
    resolve_parsed_root,
)
from app.services.conversation import (
    ConversationKnowledgeBaseMismatchError,
    ConversationNotFoundError,
    get_or_create_conversation_for_question,
    persist_question_answer_exchange,
)
from app.services.qa import AnswerGenerationError, answer_question
from app.services.retrieval import (
    RetrievalMode,
    RetrievalRequest,
    retrieve as retrieve_knowledge,
)
from app.services.source_locator import (
    build_preview_target_for_chunk,
    build_source_locator_for_chunk,
)
from app.services.document_task import (
    ActiveDocumentTaskExistsError,
    DocumentTaskEligibilityError,
    create_document_task_for_document,
)
from app.services.processing_job import (
    ActiveProcessingJobExistsError,
    ProcessingJobEligibilityError,
    ProcessingJobSourceMissingError,
    can_retry_document_processing_job,
    count_active_processing_jobs_for_knowledge_base,
    count_active_processing_jobs_for_user,
    count_processing_jobs_by_status_for_knowledge_base,
    count_processing_jobs_for_knowledge_base,
    get_active_processing_job_for_document,
    list_processing_jobs_for_knowledge_base,
    list_processing_jobs_for_document,
    retry_document_processing_job,
)
from app.services import processing_worker
from app.services.upload_guard import (
    DUPLICATE_DOCUMENT,
    UploadGuardError,
    build_upload_error_detail,
    read_and_validate_upload_file,
    validate_active_job_limits,
)
from app.services.knowledge_base import (
    UNSET,
    create_team_knowledge_base,
    delete_knowledge_base,
    get_team_knowledge_base,
    list_team_knowledge_bases,
    update_knowledge_base,
)
from app.services.knowledge_base_health import build_knowledge_base_rag_health
from app.services.knowledge_graph.graph_browser import (
    get_graph_entity_detail,
    list_graph_entities,
)
from app.services.knowledge_graph.graph_export_service import export_graph
from app.services.knowledge_graph.graph_index_service import (
    cleanup_orphan_entities,
    deduplicate_relations,
    rebuild_document_graph,
)
from app.services.team import get_team_membership


router = APIRouter(prefix="/teams/{team_id}/knowledge-bases", tags=["team-knowledge-bases"])
logger = logging.getLogger("purelink.uploads")


def _build_processing_job_submission(job) -> ProcessingJobSubmissionRead:
    return ProcessingJobSubmissionRead(
        document_id=job.document_id,
        document_status=job.document.processing_status,
        job_id=job.id,
        job_type=job.job_type,
        job_status=job.status,
        trigger_type=job.trigger_type,
        attempt_number=job.attempt_number,
    )


def _build_processing_job_summary(db: DBSession, job, *, upload_root) -> ProcessingJobSummaryRead:
    filename = job.document.original_filename if job.document is not None else ""
    return ProcessingJobSummaryRead(
        id=job.id,
        job_id=job.id,
        document_id=job.document_id,
        document_status=job.document.processing_status,
        filename=filename,
        status=job.status,
        job_status=job.status,
        current_step=job.current_step,
        error_code=job.error_code,
        error_message=job.error_message,
        attempt_count=job.attempt_number,
        attempt_number=job.attempt_number,
        max_attempts=job.max_retries + 1,
        retry_count=job.retry_count,
        max_retries=job.max_retries,
        can_retry=can_retry_document_processing_job(db, job=job, upload_root=upload_root),
        job_type=job.job_type,
        trigger_type=job.trigger_type,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def _build_processing_job_list(
    db: DBSession,
    *,
    knowledge_base_id: int,
    jobs: list,
    total: int,
    upload_root,
) -> ProcessingJobListRead:
    counts = count_processing_jobs_by_status_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base_id,
    )
    return ProcessingJobListRead(
        items=[
            _build_processing_job_summary(db, job, upload_root=upload_root)
            for job in jobs
        ],
        total=total,
        failed_count=counts.get(ProcessingJobStatus.FAILED, 0)
        + counts.get(ProcessingJobStatus.CANCELLED, 0),
        running_count=counts.get(ProcessingJobStatus.QUEUED, 0)
        + counts.get(ProcessingJobStatus.PROCESSING, 0)
        + counts.get(ProcessingJobStatus.RETRYING, 0),
        completed_count=counts.get(ProcessingJobStatus.SUCCEEDED, 0),
    )


def _raise_processing_retry_error(exc: Exception) -> None:
    if isinstance(exc, ActiveProcessingJobExistsError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "PROCESSING_JOB_ALREADY_RUNNING",
                "message": str(exc),
            },
        ) from exc
    if isinstance(exc, ProcessingJobSourceMissingError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "PROCESSING_SOURCE_MISSING",
                "message": str(exc),
            },
        ) from exc
    if isinstance(exc, ProcessingJobEligibilityError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "PROCESSING_RETRY_NOT_ALLOWED",
                "message": str(exc),
            },
        ) from exc
    raise exc


def _raise_upload_guard_error(exc: UploadGuardError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail=build_upload_error_detail(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
        ),
    ) from exc


def _raise_duplicate_document(document_id: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error_code": DUPLICATE_DOCUMENT,
            "message": "This file already exists in the knowledge base.",
            "document_id": str(document_id),
        },
    )


def _is_team_document_reindex_eligible(document: object) -> bool:
    review_status = getattr(document, "review_status", None)
    processing_status = getattr(document, "processing_status", None)
    return review_status == DocumentReviewStatus.APPROVED and processing_status in {
        DocumentProcessingStatus.READY,
        DocumentProcessingStatus.PARSED,
        DocumentProcessingStatus.INDEXED,
    }


def _get_active_membership_or_404(
    db: DBSession,
    *,
    team_id: int,
    user_id: int,
):
    membership = get_team_membership(
        db,
        team_id=team_id,
        user_id=user_id,
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found.",
        )
    return membership


def _get_admin_membership_or_raise(
    db: DBSession,
    *,
    team_id: int,
    user_id: int,
):
    membership = _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=user_id,
    )
    if membership.role != TeamMemberRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return membership


def _get_team_knowledge_base_or_404(
    db: DBSession,
    *,
    team_id: int,
    knowledge_base_id: int,
):
    knowledge_base = get_team_knowledge_base(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )
    return knowledge_base


@router.post("", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
async def create_team_knowledge_base_endpoint(
    team_id: int,
    payload: TeamKnowledgeBaseCreateRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeBaseRead:
    _get_admin_membership_or_raise(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = create_team_knowledge_base(
        db,
        team_id=team_id,
        name=payload.name,
        description=payload.description,
    )
    return KnowledgeBaseRead.model_validate(knowledge_base)


@router.get("", response_model=list[KnowledgeBaseRead])
async def list_team_knowledge_bases_endpoint(
    team_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> list[KnowledgeBaseRead]:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_bases = list_team_knowledge_bases(db, team_id=team_id)
    return [KnowledgeBaseRead.model_validate(item) for item in knowledge_bases]


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
async def get_team_knowledge_base_endpoint(
    team_id: int,
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeBaseRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    return KnowledgeBaseRead.model_validate(knowledge_base)


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
async def update_team_knowledge_base_endpoint(
    team_id: int,
    knowledge_base_id: int,
    payload: TeamKnowledgeBaseUpdateRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeBaseRead:
    _get_admin_membership_or_raise(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    update_data = payload.model_dump(exclude_unset=True)
    updated = update_knowledge_base(
        db,
        knowledge_base=knowledge_base,
        name=update_data.get("name"),
        description=update_data.get("description", UNSET),
    )
    return KnowledgeBaseRead.model_validate(updated)


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team_knowledge_base_endpoint(
    team_id: int,
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> Response:
    _get_admin_membership_or_raise(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    delete_knowledge_base(db, knowledge_base=knowledge_base)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{knowledge_base_id}/rag-health", response_model=KnowledgeBaseRagHealthRead)
async def get_team_knowledge_base_rag_health_endpoint(
    team_id: int,
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeBaseRagHealthRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    return KnowledgeBaseRagHealthRead.model_validate(
        build_knowledge_base_rag_health(db, knowledge_base_id=knowledge_base.id)
    )


@router.get("/{knowledge_base_id}/graph/entities", response_model=KnowledgeGraphEntityListRead)
async def list_team_knowledge_base_graph_entities_endpoint(
    team_id: int,
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
    q: str | None = Query(default=None, max_length=120),
) -> KnowledgeGraphEntityListRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    return list_graph_entities(db, knowledge_base_id=knowledge_base.id, query=q)


@router.get(
    "/{knowledge_base_id}/graph/entities/{entity_id}",
    response_model=KnowledgeGraphEntityDetailRead,
)
async def get_team_knowledge_base_graph_entity_endpoint(
    team_id: int,
    knowledge_base_id: int,
    entity_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeGraphEntityDetailRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    detail = get_graph_entity_detail(
        db,
        knowledge_base_id=knowledge_base.id,
        entity_id=entity_id,
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Graph entity not found.",
        )
    return detail


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/graph/rebuild",
    response_model=KnowledgeGraphDocumentRebuildRead,
)
async def rebuild_team_document_graph_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeGraphDocumentRebuildRead:
    _get_admin_membership_or_raise(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    result = rebuild_document_graph(db, document_id=document.id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    db.commit()
    return KnowledgeGraphDocumentRebuildRead.model_validate(result, from_attributes=True)


@router.post(
    "/{knowledge_base_id}/graph/cleanup-orphans",
    response_model=KnowledgeGraphCleanupRead,
)
async def cleanup_team_graph_orphans_endpoint(
    team_id: int,
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeGraphCleanupRead:
    _get_admin_membership_or_raise(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    result = cleanup_orphan_entities(db, kb_id=knowledge_base.id)
    db.commit()
    return KnowledgeGraphCleanupRead.model_validate(result, from_attributes=True)


@router.post(
    "/{knowledge_base_id}/graph/deduplicate-relations",
    response_model=KnowledgeGraphDeduplicationRead,
)
async def deduplicate_team_graph_relations_endpoint(
    team_id: int,
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeGraphDeduplicationRead:
    _get_admin_membership_or_raise(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    result = deduplicate_relations(db, kb_id=knowledge_base.id)
    db.commit()
    return KnowledgeGraphDeduplicationRead.model_validate(result, from_attributes=True)


@router.get("/{knowledge_base_id}/graph/export", response_model=KnowledgeGraphExportRead)
async def export_team_graph_endpoint(
    team_id: int,
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
    q: str | None = Query(default=None, max_length=120),
    relation_type: str | None = Query(default=None, max_length=80),
    entity_id: int | None = Query(default=None, ge=1),
    limit_entities: int = Query(default=100, ge=1, le=500),
    limit_relations: int = Query(default=300, ge=1, le=1000),
    limit_sources_per_relation: int = Query(default=5, ge=1, le=10),
    entity_limit: int | None = Query(default=None, ge=1, le=500),
    relation_limit: int | None = Query(default=None, ge=1, le=1000),
    sources_per_relation: int | None = Query(default=None, ge=1, le=10),
) -> KnowledgeGraphExportRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    result = export_graph(
        db,
        kb_id=knowledge_base.id,
        q=q,
        relation_type=relation_type,
        entity_id=entity_id,
        limit_entities=limit_entities,
        limit_relations=limit_relations,
        limit_sources_per_relation=limit_sources_per_relation,
        entity_limit=entity_limit,
        relation_limit=relation_limit,
        sources_per_relation=sources_per_relation,
    )
    return KnowledgeGraphExportRead.model_validate(result, from_attributes=True)


@router.post(
    "/{knowledge_base_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_to_team_knowledge_base_endpoint(
    team_id: int,
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> DocumentRead:
    started_at = time.monotonic()
    membership = _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )

    settings = get_settings()
    try:
        upload = await read_and_validate_upload_file(
            file,
            max_upload_size_mb=settings.max_upload_size_mb,
            allowed_extensions=settings.allowed_upload_extensions,
            allowed_mime_types=settings.allowed_upload_mime_types,
        )
    except UploadGuardError as exc:
        logger.warning(
            "team document upload rejected user_id=%s knowledge_base_id=%s filename=%s file_size=%s "
            "sha256=%s duplicate=%s job_id=%s duration_ms=%s error_code=%s",
            current_user.id,
            knowledge_base.id,
            file.filename,
            None,
            None,
            False,
            None,
            int((time.monotonic() - started_at) * 1000),
            exc.error_code,
        )
        _raise_upload_guard_error(exc)

    content = upload.content
    file_size = upload.file_size
    file_sha256 = compute_document_sha256(content)
    duplicate_document = get_document_by_sha256_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        sha256=file_sha256,
    )
    if duplicate_document is not None:
        logger.info(
            "team document upload duplicate user_id=%s knowledge_base_id=%s filename=%s file_size=%s "
            "sha256=%s duplicate=%s job_id=%s duration_ms=%s error_code=%s",
            current_user.id,
            knowledge_base.id,
            upload.filename,
            file_size,
            file_sha256,
            True,
            duplicate_document.latest_processing_job_id,
            int((time.monotonic() - started_at) * 1000),
            DUPLICATE_DOCUMENT,
        )
        _raise_duplicate_document(duplicate_document.id)

    is_admin_upload = membership.role == TeamMemberRole.ADMIN
    if is_admin_upload:
        try:
            validate_active_job_limits(
                active_jobs_for_user=count_active_processing_jobs_for_user(
                    db,
                    user_id=current_user.id,
                ),
                max_active_jobs_per_user=settings.max_active_jobs_per_user,
                active_jobs_for_knowledge_base=count_active_processing_jobs_for_knowledge_base(
                    db,
                    knowledge_base_id=knowledge_base.id,
                ),
                max_active_jobs_per_kb=settings.max_active_jobs_per_kb,
            )
        except UploadGuardError as exc:
            logger.warning(
                "team document upload rejected user_id=%s knowledge_base_id=%s filename=%s file_size=%s "
                "sha256=%s duplicate=%s job_id=%s duration_ms=%s error_code=%s",
                current_user.id,
                knowledge_base.id,
                upload.filename,
                file_size,
                file_sha256,
                False,
                None,
                int((time.monotonic() - started_at) * 1000),
                exc.error_code,
            )
            _raise_upload_guard_error(exc)

    upload_root = resolve_upload_root(settings.upload_dir, base_dir=BASE_DIR)
    internal_filename, storage_path = store_document_file(
        upload_root=upload_root,
        scope=KnowledgeBaseScope.TEAM,
        team_id=team_id,
        knowledge_base_id=knowledge_base.id,
        original_filename=upload.filename,
        content=content,
    )
    try:
        document = create_document(
            db,
            knowledge_base_id=knowledge_base.id,
            owner_id=current_user.id,
            submitted_by=current_user.id,
            filename=internal_filename,
            original_filename=upload.filename,
            file_type=upload.content_type,
            file_size=file_size,
            storage_path=storage_path,
            review_status=(
                DocumentReviewStatus.APPROVED
                if is_admin_upload
                else DocumentReviewStatus.PENDING_REVIEW
            ),
            processing_status=DocumentProcessingStatus.UPLOADED,
            sha256=file_sha256,
        )
    except IntegrityError as exc:
        db.rollback()
        (upload_root / storage_path).unlink(missing_ok=True)
        duplicate_document = get_document_by_sha256_for_knowledge_base(
            db,
            knowledge_base_id=knowledge_base.id,
            sha256=file_sha256,
        )
        logger.info(
            "team document upload duplicate race user_id=%s knowledge_base_id=%s filename=%s file_size=%s "
            "sha256=%s duplicate=%s job_id=%s duration_ms=%s error_code=%s",
            current_user.id,
            knowledge_base.id,
            upload.filename,
            file_size,
            file_sha256,
            True,
            duplicate_document.latest_processing_job_id if duplicate_document else None,
            int((time.monotonic() - started_at) * 1000),
            DUPLICATE_DOCUMENT,
        )
        if duplicate_document is not None:
            _raise_duplicate_document(duplicate_document.id)
        raise exc

    job_id = None
    if is_admin_upload:
        document.reviewed_by = current_user.id
        document.reviewed_at = datetime.now(UTC)
        document.review_comment = None
        db.commit()
        db.refresh(document)
        try:
            job = processing_worker.create_and_submit_processing_job(
                db,
                document=document,
                triggered_by_id=current_user.id,
            )
        except RuntimeError as exc:
            logger.warning(
                "team document upload job submit failed user_id=%s knowledge_base_id=%s filename=%s file_size=%s "
                "sha256=%s duplicate=%s job_id=%s duration_ms=%s error_code=%s",
                current_user.id,
                knowledge_base.id,
                upload.filename,
                file_size,
                file_sha256,
                False,
                document.latest_processing_job_id,
                int((time.monotonic() - started_at) * 1000),
                "PROCESSING_JOB_SUBMIT_FAILED",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc
        job_id = job.id
        db.refresh(document)
    logger.info(
        "team document upload accepted user_id=%s knowledge_base_id=%s filename=%s file_size=%s "
        "sha256=%s duplicate=%s job_id=%s duration_ms=%s error_code=%s",
        current_user.id,
        knowledge_base.id,
        upload.filename,
        file_size,
        file_sha256,
        False,
        job_id,
        int((time.monotonic() - started_at) * 1000),
        None,
    )
    return DocumentRead.model_validate(document)


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentRead])
async def list_team_knowledge_base_documents_endpoint(
    team_id: int,
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> list[DocumentRead]:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    documents = list_documents_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
    )
    return [DocumentRead.model_validate(item) for item in documents]


@router.get(
    "/{knowledge_base_id}/documents/{document_id}/rag-debug",
    response_model=DocumentRagDebugRead,
)
async def get_team_document_rag_debug_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentRagDebugRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    return DocumentRagDebugRead.model_validate(
        build_document_rag_debug(db, document=document)
    )


@router.get(
    "/{knowledge_base_id}/documents/{document_id}/status",
    response_model=DocumentStatusRead,
)
async def get_team_document_status_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentStatusRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    return DocumentStatusRead.model_validate(build_document_status(db, document=document))


@router.get(
    "/{knowledge_base_id}/documents/{document_id}/preview",
    response_model=DocumentPreviewRead,
)
async def get_team_document_preview_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentPreviewRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return build_document_preview(db, document=document)


@router.get("/{knowledge_base_id}/documents/{document_id}/file")
async def get_team_document_file_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> Response:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    settings = get_settings()
    upload_root = resolve_upload_root(settings.upload_dir, base_dir=BASE_DIR)
    source_path = resolve_document_file_path(upload_root=upload_root, document=document)
    if not source_path.exists() or not source_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found.",
        )

    return Response(
        content=source_path.read_bytes(),
        media_type=document.file_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{document.original_filename}"',
        },
    )


@router.delete(
    "/{knowledge_base_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_team_document_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> Response:
    membership = _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if membership.role != TeamMemberRole.ADMIN and document.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team admins or the document owner can delete this file.",
        )

    settings = get_settings()
    upload_root = resolve_upload_root(settings.upload_dir, base_dir=BASE_DIR)
    parsed_root = resolve_parsed_root(settings.parsed_dir, base_dir=BASE_DIR)
    chunks_root = resolve_chunks_root(settings.chunks_dir, base_dir=BASE_DIR)
    vector_root = resolve_vector_store_root(settings.vector_store_dir, base_dir=BASE_DIR)

    delete_document_and_artifacts(
        db,
        document=document,
        scope=KnowledgeBaseScope.TEAM,
        team_id=team_id,
        upload_root=upload_root,
        parsed_root=parsed_root,
        chunks_root=chunks_root,
    )
    delete_document_from_knowledge_base_index(
        vector_root=vector_root,
        scope=KnowledgeBaseScope.TEAM,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
        team_id=team_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/process",
    response_model=ProcessingJobSubmissionRead,
)
async def process_team_document_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> ProcessingJobSubmissionRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if document.review_status != DocumentReviewStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not eligible for processing.",
        )

    try:
        job = processing_worker.create_and_submit_processing_job(
            db,
            document=document,
            triggered_by_id=current_user.id,
        )
    except (ActiveProcessingJobExistsError, ProcessingJobEligibilityError) as exc:
        active_job = get_active_processing_job_for_document(
            db,
            document_id=document.id,
            job_type=ProcessingJobType.DOCUMENT_PROCESS,
        )
        if active_job is not None:
            return _build_processing_job_submission(active_job)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return _build_processing_job_submission(job)


@router.get(
    "/{knowledge_base_id}/processing-jobs",
    response_model=ProcessingJobListRead,
)
async def list_team_processing_jobs_endpoint(
    team_id: int,
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
    job_status: ProcessingJobStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ProcessingJobListRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    settings = get_settings()
    upload_root = resolve_upload_root(settings.upload_dir, base_dir=BASE_DIR)
    jobs = list_processing_jobs_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        status_filter=job_status,
        search=search,
        limit=limit,
        offset=offset,
    )
    total = count_processing_jobs_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        status_filter=job_status,
        search=search,
    )
    return _build_processing_job_list(
        db,
        knowledge_base_id=knowledge_base.id,
        jobs=jobs,
        total=total,
        upload_root=upload_root,
    )


@router.get(
    "/{knowledge_base_id}/documents/{document_id}/processing-jobs",
    response_model=list[ProcessingJobRead],
)
async def list_team_document_processing_jobs_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> list[ProcessingJobRead]:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    jobs = list_processing_jobs_for_document(
        db,
        document_id=document.id,
    )
    return [ProcessingJobRead.model_validate(item) for item in jobs]


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/retry-process",
    response_model=ProcessingJobSummaryRead,
)
@router.post(
    "/{knowledge_base_id}/documents/{document_id}/retry-processing",
    response_model=ProcessingJobSummaryRead,
)
async def retry_team_document_processing_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> ProcessingJobSubmissionRead:
    _get_admin_membership_or_raise(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if document.review_status != DocumentReviewStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "PROCESSING_RETRY_NOT_ALLOWED",
                "message": "Document is not eligible for processing.",
            },
        )

    try:
        settings = get_settings()
        upload_root = resolve_upload_root(settings.upload_dir, base_dir=BASE_DIR)
        job = retry_document_processing_job(
            db,
            document=document,
            triggered_by_id=current_user.id,
            upload_root=upload_root,
        )
        processing_worker.submit_processing_job(job=job)
    except (ActiveProcessingJobExistsError, ProcessingJobEligibilityError) as exc:
        _raise_processing_retry_error(exc)
    except ProcessingJobSourceMissingError as exc:
        _raise_processing_retry_error(exc)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "DOCUMENT_PROCESSING_FAILED",
                "message": str(exc),
            },
        ) from exc
    return _build_processing_job_summary(db, job, upload_root=upload_root)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/reprocess",
    response_model=ProcessingJobSubmissionRead,
)
async def reprocess_team_document_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> ProcessingJobSubmissionRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if document.review_status != DocumentReviewStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not eligible for processing.",
        )

    try:
        job = processing_worker.create_and_submit_processing_job(
            db,
            document=document,
            triggered_by_id=current_user.id,
            trigger_type=ProcessingJobTrigger.REPROCESS,
        )
    except (ActiveProcessingJobExistsError, ProcessingJobEligibilityError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return _build_processing_job_submission(job)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/parse",
    response_model=DocumentParseRead,
)
async def parse_team_document_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentParseRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if document.review_status != DocumentReviewStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not eligible for parsing.",
        )

    settings = get_settings()
    upload_root = resolve_upload_root(settings.upload_dir, base_dir=BASE_DIR)
    parsed_root = resolve_parsed_root(settings.parsed_dir, base_dir=BASE_DIR)

    try:
        parsed_result = parse_document_to_local_result(
            document=document,
            upload_root=upload_root,
            parsed_root=parsed_root,
            scope=KnowledgeBaseScope.TEAM,
            team_id=team_id,
        )
    except DocumentParseError as exc:
        update_document_processing_status(
            db,
            document=document,
            processing_status=DocumentProcessingStatus.FAILED,
            error_message=str(exc),
            processed_at=None,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    update_document_processing_status(
        db,
        document=document,
        processing_status=DocumentProcessingStatus.PARSED,
        error_message=None,
    )
    return DocumentParseRead(
        document_id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        processing_status=document.processing_status,
        parsed_path=parsed_result.parsed_path,
        parser=parsed_result.parser,
        extracted_char_count=parsed_result.extracted_char_count,
    )


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/chunk",
    response_model=DocumentChunkRead,
)
async def chunk_team_document_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentChunkRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if document.review_status != DocumentReviewStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not eligible for chunking.",
        )
    if document.processing_status != DocumentProcessingStatus.PARSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document must be parsed before chunking.",
        )

    settings = get_settings()
    parsed_root = resolve_parsed_root(settings.parsed_dir, base_dir=BASE_DIR)
    chunks_root = resolve_chunks_root(settings.chunks_dir, base_dir=BASE_DIR)
    try:
        chunked_result = chunk_document_from_parsed_result(
            document=document,
            parsed_root=parsed_root,
            chunks_root=chunks_root,
            scope=KnowledgeBaseScope.TEAM,
            team_id=team_id,
        )
    except DocumentChunkError as exc:
        update_document_processing_status(
            db,
            document=document,
            processing_status=DocumentProcessingStatus.FAILED,
            error_message=str(exc),
            processed_at=None,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return DocumentChunkRead(
        document_id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        processing_status=document.processing_status,
        chunked_path=chunked_result.chunked_path,
        source_parsed_path=chunked_result.source_parsed_path,
        chunk_count=chunked_result.chunk_count,
        chunk_size=chunked_result.chunk_size,
    )


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/embed",
    response_model=ProcessingJobSubmissionRead,
)
@router.post(
    "/{knowledge_base_id}/documents/{document_id}/reindex",
    response_model=ProcessingJobSubmissionRead,
)
async def embed_team_document_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> ProcessingJobSubmissionRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    if document.review_status != DocumentReviewStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not eligible for embedding.",
        )
    if document.processing_status not in {
        DocumentProcessingStatus.READY,
        DocumentProcessingStatus.PARSED,
        DocumentProcessingStatus.INDEXED,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document must be ready or chunked before embedding.",
        )

    try:
        job = processing_worker.create_and_submit_indexing_job(
            db,
            document=document,
            triggered_by_id=current_user.id,
        )
    except (ActiveProcessingJobExistsError, ProcessingJobEligibilityError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return _build_processing_job_submission(job)


@router.post(
    "/{knowledge_base_id}/reindex",
    response_model=KnowledgeBaseReindexRead,
)
async def reindex_team_knowledge_base_endpoint(
    team_id: int,
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeBaseReindexRead:
    membership = _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    if membership.role != TeamMemberRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team admins can reindex the knowledge base.",
        )

    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    documents = list_documents_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
    )
    eligible_documents = [
        document for document in documents if _is_team_document_reindex_eligible(document)
    ]
    eligible_document_ids = {document.id for document in eligible_documents}
    skipped_document_ids: list[int] = [
        document.id for document in documents if document.id not in eligible_document_ids
    ]

    settings = get_settings()
    vector_root = resolve_vector_store_root(settings.vector_store_dir, base_dir=BASE_DIR)
    if eligible_documents:
        delete_knowledge_base_index_artifact(
            vector_root=vector_root,
            scope=KnowledgeBaseScope.TEAM,
            knowledge_base_id=knowledge_base.id,
            team_id=team_id,
        )

    queued_jobs: list[ProcessingJobSubmissionRead] = []
    for document in eligible_documents:
        try:
            job = processing_worker.create_and_submit_indexing_job(
                db,
                document=document,
                triggered_by_id=current_user.id,
            )
        except (ActiveProcessingJobExistsError, ProcessingJobEligibilityError):
            skipped_document_ids.append(document.id)
            continue
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(exc),
            ) from exc
        queued_jobs.append(_build_processing_job_submission(job))

    return KnowledgeBaseReindexRead(
        knowledge_base_id=knowledge_base.id,
        queued_jobs=queued_jobs,
        queued_document_ids=[job.document_id for job in queued_jobs],
        skipped_document_ids=sorted(set(skipped_document_ids)),
    )


@router.post(
    "/{knowledge_base_id}/retrieve",
    response_model=RetrievalResponse,
)
async def retrieve_team_knowledge_base_chunks_endpoint(
    team_id: int,
    knowledge_base_id: int,
    payload: RetrievalQueryRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> RetrievalResponse:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    documents = list_documents_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
    )

    settings = get_settings()
    vector_root = resolve_vector_store_root(settings.vector_store_dir, base_dir=BASE_DIR)
    try:
        retrieval_result = await retrieve_knowledge(
            RetrievalRequest(
                db=db,
                documents=documents,
                vector_root=vector_root,
                scope=KnowledgeBaseScope.TEAM,
                knowledge_base_id=knowledge_base.id,
                user_id=current_user.id,
                team_id=team_id,
                query=payload.query,
                top_k=payload.top_k,
                mode=RetrievalMode(payload.mode),
                include_citations=False,
                required_review_status=DocumentReviewStatus.APPROVED,
            )
        )
    except DocumentEmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    results = retrieval_result.metadata.get("retrieved_chunks", [])

    return RetrievalResponse(
        query=payload.query,
        top_k=payload.top_k,
        mode=retrieval_result.mode.value,
        requested_mode=retrieval_result.requested_mode.value if retrieval_result.requested_mode else None,
        selected_mode=retrieval_result.selected_mode.value if retrieval_result.selected_mode else None,
        router_reason=retrieval_result.router_reason,
        used_reranker=retrieval_result.used_reranker,
        trace_id=retrieval_result.trace_id,
        results=[
            RetrievedChunkRead(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                knowledge_base_id=item.knowledge_base_id,
                scope=item.scope,
                team_id=item.team_id,
                document_name=item.document_name,
                snippet=item.snippet,
                text=item.text,
                source_type=item.source_type,
                char_start=item.char_start,
                char_end=item.char_end,
                page_number=item.page_number,
                start_time=item.start_time,
                end_time=item.end_time,
                section_title=item.section_title,
                source_locator=build_source_locator_for_chunk(item),
                preview_target=build_preview_target_for_chunk(item),
                heading_path=list(item.heading_path) if item.heading_path else None,
                score=item.score,
                vector_score=item.vector_score,
                keyword_score=item.keyword_score,
                graph_score=item.graph_score,
                matched_terms=list(item.matched_terms) if item.matched_terms else None,
                candidate_sources=list(item.candidate_sources) if item.candidate_sources else None,
            )
            for item in results
        ],
    )


@router.post(
    "/{knowledge_base_id}/ask",
    response_model=QuestionAnswerResponse,
)
async def ask_team_knowledge_base_endpoint(
    team_id: int,
    knowledge_base_id: int,
    payload: QuestionAnswerRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> QuestionAnswerResponse:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    documents = list_documents_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
    )

    settings = get_settings()
    vector_root = resolve_vector_store_root(settings.vector_store_dir, base_dir=BASE_DIR)
    try:
        retrieval_result = await retrieve_knowledge(
            RetrievalRequest(
                db=db,
                documents=documents,
                vector_root=vector_root,
                scope=KnowledgeBaseScope.TEAM,
                knowledge_base_id=knowledge_base.id,
                user_id=current_user.id,
                team_id=team_id,
                query=payload.question,
                evidence_query=payload.question,
                top_k=payload.top_k,
                mode=RetrievalMode(payload.mode),
                required_review_status=DocumentReviewStatus.APPROVED,
            )
        )
    except DocumentEmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        qa_result = answer_question(
            db=db,
            question=payload.question,
            retrieved_chunks=retrieval_result.metadata.get("retrieved_chunks", []),
            documents=documents,
            knowledge_base_id=knowledge_base.id,
            scope=KnowledgeBaseScope.TEAM,
            team_id=team_id,
            required_review_status=DocumentReviewStatus.APPROVED,
            retrieval_result=retrieval_result,
        )
    except AnswerGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    try:
        conversation = get_or_create_conversation_for_question(
            db,
            user_id=current_user.id,
            knowledge_base_id=knowledge_base.id,
            question=payload.question,
            conversation_id=payload.conversation_id,
        )
        persist_question_answer_exchange(
            db,
            conversation=conversation,
            question=payload.question,
            answer=qa_result.answer,
            citations=qa_result.citations,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ConversationKnowledgeBaseMismatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return QuestionAnswerResponse(
        conversation_id=conversation.id,
        answer=qa_result.answer,
        citations=qa_result.citations,
        intent=qa_result.intent,
        retrieval_mode=retrieval_result.mode.value,
        requested_mode=retrieval_result.requested_mode.value if retrieval_result.requested_mode else None,
        selected_mode=retrieval_result.selected_mode.value if retrieval_result.selected_mode else None,
        router_reason=retrieval_result.router_reason,
        used_reranker=retrieval_result.used_reranker,
        trace_id=retrieval_result.trace_id,
    )


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/parse-tasks",
    response_model=DocumentTaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_team_document_parse_task_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    try:
        task = create_document_task_for_document(
            db,
            document=document,
            task_type=DocumentTaskType.PARSE,
            scope=KnowledgeBaseScope.TEAM,
            team_id=team_id,
        )
    except ActiveDocumentTaskExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DocumentTaskEligibilityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return DocumentTaskRead.model_validate(task)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/chunk-tasks",
    response_model=DocumentTaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_team_document_chunk_task_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    try:
        task = create_document_task_for_document(
            db,
            document=document,
            task_type=DocumentTaskType.CHUNK,
            scope=KnowledgeBaseScope.TEAM,
            team_id=team_id,
        )
    except ActiveDocumentTaskExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DocumentTaskEligibilityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return DocumentTaskRead.model_validate(task)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/embed-tasks",
    response_model=DocumentTaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_team_document_embed_task_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    try:
        task = create_document_task_for_document(
            db,
            document=document,
            task_type=DocumentTaskType.EMBED,
            scope=KnowledgeBaseScope.TEAM,
            team_id=team_id,
        )
    except ActiveDocumentTaskExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DocumentTaskEligibilityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return DocumentTaskRead.model_validate(task)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/index-tasks",
    response_model=DocumentTaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_team_document_index_task_endpoint(
    team_id: int,
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    _get_active_membership_or_404(
        db,
        team_id=team_id,
        user_id=current_user.id,
    )
    knowledge_base = _get_team_knowledge_base_or_404(
        db,
        team_id=team_id,
        knowledge_base_id=knowledge_base_id,
    )
    document = get_document_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    try:
        task = create_document_task_for_document(
            db,
            document=document,
            task_type=DocumentTaskType.INDEX,
            scope=KnowledgeBaseScope.TEAM,
            team_id=team_id,
        )
    except ActiveDocumentTaskExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DocumentTaskEligibilityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return DocumentTaskRead.model_validate(task)
