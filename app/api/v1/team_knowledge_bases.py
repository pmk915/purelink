from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.api.deps import CurrentUser, DBSession
from app.core.config import BASE_DIR, get_settings
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    DocumentTaskType,
    KnowledgeBaseScope,
    ProcessingJobTrigger,
    TeamMemberRole,
)
from app.schemas.document import (
    DocumentChunkRead,
    DocumentParseRead,
    DocumentPreviewRead,
    DocumentRead,
    RetrievalQueryRequest,
    RetrievalResponse,
    RetrievedChunkRead,
)
from app.schemas.qa import QuestionAnswerRequest, QuestionAnswerResponse
from app.schemas.document_task import DocumentTaskRead
from app.schemas.processing_job import ProcessingJobRead, ProcessingJobSubmissionRead
from app.schemas.knowledge_base import (
    KnowledgeBaseRead,
    TeamKnowledgeBaseCreateRequest,
    TeamKnowledgeBaseUpdateRequest,
)
from app.services.document import (
    create_document,
    ensure_supported_document_upload,
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
    DocumentEmbeddingError,
    resolve_vector_store_root,
)
from app.services.document_preview import (
    build_document_preview,
    resolve_document_file_path,
)
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
from app.services.retrieval import retrieve_chunks_for_documents
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
    list_processing_jobs_for_document,
)
from app.services import processing_worker
from app.services.knowledge_base import (
    UNSET,
    create_team_knowledge_base,
    delete_knowledge_base,
    get_team_knowledge_base,
    list_team_knowledge_bases,
    update_knowledge_base,
)
from app.services.team import get_team_membership


router = APIRouter(prefix="/teams/{team_id}/knowledge-bases", tags=["team-knowledge-bases"])


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

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a filename.",
        )
    try:
        ensure_supported_document_upload(
            filename=file.filename,
            mime_type=file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    settings = get_settings()
    upload_root = resolve_upload_root(settings.upload_dir, base_dir=BASE_DIR)
    internal_filename, storage_path = store_document_file(
        upload_root=upload_root,
        scope=KnowledgeBaseScope.TEAM,
        team_id=team_id,
        knowledge_base_id=knowledge_base.id,
        original_filename=file.filename,
        content=content,
    )
    is_admin_upload = membership.role == TeamMemberRole.ADMIN
    document = create_document(
        db,
        knowledge_base_id=knowledge_base.id,
        owner_id=current_user.id,
        submitted_by=current_user.id,
        filename=internal_filename,
        original_filename=file.filename,
        file_type=file.content_type or "application/octet-stream",
        file_size=len(content),
        storage_path=storage_path,
        review_status=(
            DocumentReviewStatus.APPROVED
            if is_admin_upload
            else DocumentReviewStatus.PENDING_REVIEW
        ),
        processing_status=DocumentProcessingStatus.UPLOADED,
    )
    if is_admin_upload:
        document.reviewed_by = current_user.id
        document.reviewed_at = datetime.now(UTC)
        document.review_comment = None
        db.commit()
        db.refresh(document)
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
    response_model=ProcessingJobSubmissionRead,
)
async def retry_team_document_processing_endpoint(
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
            trigger_type=ProcessingJobTrigger.RETRY,
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
        results = retrieve_chunks_for_documents(
            db=db,
            documents=documents,
            vector_root=vector_root,
            scope=KnowledgeBaseScope.TEAM,
            knowledge_base_id=knowledge_base.id,
            team_id=team_id,
            query=payload.query,
            top_k=payload.top_k,
            required_review_status=DocumentReviewStatus.APPROVED,
        )
    except DocumentEmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return RetrievalResponse(
        query=payload.query,
        top_k=payload.top_k,
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
        retrieved_chunks = retrieve_chunks_for_documents(
            db=db,
            documents=documents,
            vector_root=vector_root,
            scope=KnowledgeBaseScope.TEAM,
            knowledge_base_id=knowledge_base.id,
            team_id=team_id,
            query=payload.question,
            top_k=payload.top_k,
            required_review_status=DocumentReviewStatus.APPROVED,
        )
    except DocumentEmbeddingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    try:
        qa_result = answer_question(
            question=payload.question,
            retrieved_chunks=retrieved_chunks,
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
