from __future__ import annotations

import logging
import time

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DBSession
from app.core.config import BASE_DIR, get_settings
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    DocumentTaskType,
    KnowledgeBaseScope,
    ProcessingJobTrigger,
    ProcessingJobType,
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
    KnowledgeBaseCreateRequest,
    KnowledgeBaseRead,
    KnowledgeBaseReindexRead,
    KnowledgeBaseUpdateRequest,
)
from app.services.document import (
    compute_document_sha256,
    create_document,
    delete_document_and_artifacts,
    DocumentUploadSupportError,
    ensure_supported_document_upload,
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
    count_active_processing_jobs_for_knowledge_base,
    count_active_processing_jobs_for_user,
    get_active_processing_job_for_document,
    list_processing_jobs_for_document,
)
from app.services import processing_worker
from app.services.upload_guard import (
    DUPLICATE_DOCUMENT,
    UploadGuardError,
    build_upload_error_detail,
    validate_active_job_limits,
    validate_upload_size,
)
from app.services.knowledge_base import (
    UNSET,
    create_knowledge_base,
    delete_knowledge_base,
    get_knowledge_base_for_user,
    list_knowledge_bases_for_user,
    update_knowledge_base,
)


router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])
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


def _raise_upload_guard_error(exc: UploadGuardError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail=build_upload_error_detail(
            error_code=exc.error_code,
            message=exc.message,
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


def _is_personal_document_reindex_eligible(document: object) -> bool:
    review_status = getattr(document, "review_status", None)
    processing_status = getattr(document, "processing_status", None)
    return review_status == DocumentReviewStatus.NOT_REQUIRED and processing_status in {
        DocumentProcessingStatus.READY,
        DocumentProcessingStatus.PARSED,
        DocumentProcessingStatus.INDEXED,
    }


def _get_owned_knowledge_base_or_404(
    db: DBSession,
    *,
    knowledge_base_id: int,
    user_id: int,
):
    knowledge_base = get_knowledge_base_for_user(
        db,
        owner_id=user_id,
        knowledge_base_id=knowledge_base_id,
    )
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )
    return knowledge_base


@router.post("", response_model=KnowledgeBaseRead, status_code=status.HTTP_201_CREATED)
async def create_knowledge_base_endpoint(
    payload: KnowledgeBaseCreateRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeBaseRead:
    knowledge_base = create_knowledge_base(
        db,
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
    )
    return KnowledgeBaseRead.model_validate(knowledge_base)


@router.get("", response_model=list[KnowledgeBaseRead])
async def list_knowledge_bases_endpoint(
    db: DBSession,
    current_user: CurrentUser,
) -> list[KnowledgeBaseRead]:
    knowledge_bases = list_knowledge_bases_for_user(db, owner_id=current_user.id)
    return [KnowledgeBaseRead.model_validate(item) for item in knowledge_bases]


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
async def get_knowledge_base_endpoint(
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeBaseRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    return KnowledgeBaseRead.model_validate(knowledge_base)


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseRead)
async def update_knowledge_base_endpoint(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdateRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeBaseRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
async def delete_knowledge_base_endpoint(
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> Response:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    delete_knowledge_base(db, knowledge_base=knowledge_base)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{knowledge_base_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document_to_personal_knowledge_base_endpoint(
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> DocumentRead:
    started_at = time.monotonic()
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
    except DocumentUploadSupportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": exc.error_code,
                "message": str(exc),
            },
        ) from exc

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    settings = get_settings()
    file_size = len(content)
    try:
        validate_upload_size(
            file_size=file_size,
            max_upload_size_mb=settings.max_upload_size_mb,
        )
    except UploadGuardError as exc:
        logger.warning(
            "document upload rejected user_id=%s knowledge_base_id=%s filename=%s file_size=%s "
            "sha256=%s duplicate=%s job_id=%s duration_ms=%s error_code=%s",
            current_user.id,
            knowledge_base.id,
            file.filename,
            file_size,
            None,
            False,
            None,
            int((time.monotonic() - started_at) * 1000),
            exc.error_code,
        )
        _raise_upload_guard_error(exc)

    file_sha256 = compute_document_sha256(content)
    duplicate_document = get_document_by_sha256_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
        sha256=file_sha256,
    )
    if duplicate_document is not None:
        logger.info(
            "document upload duplicate user_id=%s knowledge_base_id=%s filename=%s file_size=%s "
            "sha256=%s duplicate=%s job_id=%s duration_ms=%s error_code=%s",
            current_user.id,
            knowledge_base.id,
            file.filename,
            file_size,
            file_sha256,
            True,
            duplicate_document.latest_processing_job_id,
            int((time.monotonic() - started_at) * 1000),
            DUPLICATE_DOCUMENT,
        )
        _raise_duplicate_document(duplicate_document.id)

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
            "document upload rejected user_id=%s knowledge_base_id=%s filename=%s file_size=%s "
            "sha256=%s duplicate=%s job_id=%s duration_ms=%s error_code=%s",
            current_user.id,
            knowledge_base.id,
            file.filename,
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
        scope=KnowledgeBaseScope.PERSONAL,
        knowledge_base_id=knowledge_base.id,
        original_filename=file.filename,
        content=content,
    )
    try:
        document = create_document(
            db,
            knowledge_base_id=knowledge_base.id,
            owner_id=current_user.id,
            submitted_by=current_user.id,
            filename=internal_filename,
            original_filename=file.filename,
            file_type=file.content_type or "application/octet-stream",
            file_size=file_size,
            storage_path=storage_path,
            review_status=DocumentReviewStatus.NOT_REQUIRED,
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
            "document upload duplicate race user_id=%s knowledge_base_id=%s filename=%s file_size=%s "
            "sha256=%s duplicate=%s job_id=%s duration_ms=%s error_code=%s",
            current_user.id,
            knowledge_base.id,
            file.filename,
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

    try:
        job = processing_worker.create_and_submit_processing_job(
            db,
            document=document,
            triggered_by_id=current_user.id,
        )
    except RuntimeError as exc:
        logger.warning(
            "document upload job submit failed user_id=%s knowledge_base_id=%s filename=%s file_size=%s "
            "sha256=%s duplicate=%s job_id=%s duration_ms=%s error_code=%s",
            current_user.id,
            knowledge_base.id,
            file.filename,
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
    db.refresh(document)
    logger.info(
        "document upload accepted user_id=%s knowledge_base_id=%s filename=%s file_size=%s "
        "sha256=%s duplicate=%s job_id=%s duration_ms=%s error_code=%s",
        current_user.id,
        knowledge_base.id,
        file.filename,
        file_size,
        file_sha256,
        False,
        job.id,
        int((time.monotonic() - started_at) * 1000),
        None,
    )
    return DocumentRead.model_validate(document)


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentRead])
async def list_personal_knowledge_base_documents_endpoint(
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> list[DocumentRead]:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
async def get_personal_document_preview_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentPreviewRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
async def get_personal_document_file_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> Response:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
async def delete_personal_document_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> Response:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
    parsed_root = resolve_parsed_root(settings.parsed_dir, base_dir=BASE_DIR)
    chunks_root = resolve_chunks_root(settings.chunks_dir, base_dir=BASE_DIR)
    vector_root = resolve_vector_store_root(settings.vector_store_dir, base_dir=BASE_DIR)

    delete_document_and_artifacts(
        db,
        document=document,
        scope=KnowledgeBaseScope.PERSONAL,
        upload_root=upload_root,
        parsed_root=parsed_root,
        chunks_root=chunks_root,
    )
    delete_document_from_knowledge_base_index(
        vector_root=vector_root,
        scope=KnowledgeBaseScope.PERSONAL,
        knowledge_base_id=knowledge_base.id,
        document_id=document_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/process",
    response_model=ProcessingJobSubmissionRead,
)
async def process_personal_document_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> ProcessingJobSubmissionRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
    if document.review_status != DocumentReviewStatus.NOT_REQUIRED:
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
    "/{knowledge_base_id}/documents/{document_id}/processing-jobs",
    response_model=list[ProcessingJobRead],
)
async def list_personal_document_processing_jobs_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> list[ProcessingJobRead]:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
async def retry_personal_document_processing_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> ProcessingJobSubmissionRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
    if document.review_status != DocumentReviewStatus.NOT_REQUIRED:
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
async def reprocess_personal_document_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> ProcessingJobSubmissionRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
    if document.review_status != DocumentReviewStatus.NOT_REQUIRED:
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
async def parse_personal_document_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentParseRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
    if document.review_status != DocumentReviewStatus.NOT_REQUIRED:
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
            scope=KnowledgeBaseScope.PERSONAL,
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
async def chunk_personal_document_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentChunkRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
    if document.review_status != DocumentReviewStatus.NOT_REQUIRED:
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
            scope=KnowledgeBaseScope.PERSONAL,
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
async def embed_personal_document_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> ProcessingJobSubmissionRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
    if document.review_status != DocumentReviewStatus.NOT_REQUIRED:
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
async def reindex_personal_knowledge_base_endpoint(
    knowledge_base_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> KnowledgeBaseReindexRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
    )
    documents = list_documents_for_knowledge_base(
        db,
        knowledge_base_id=knowledge_base.id,
    )

    eligible_documents = [
        document for document in documents if _is_personal_document_reindex_eligible(document)
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
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=knowledge_base.id,
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
async def retrieve_personal_knowledge_base_chunks_endpoint(
    knowledge_base_id: int,
    payload: RetrievalQueryRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> RetrievalResponse:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=knowledge_base.id,
            query=payload.query,
            top_k=payload.top_k,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
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
async def ask_personal_knowledge_base_endpoint(
    knowledge_base_id: int,
    payload: QuestionAnswerRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> QuestionAnswerResponse:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
            scope=KnowledgeBaseScope.PERSONAL,
            knowledge_base_id=knowledge_base.id,
            query=payload.question,
            top_k=payload.top_k,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
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
            retrieved_chunks=retrieved_chunks,
            documents=documents,
            knowledge_base_id=knowledge_base.id,
            scope=KnowledgeBaseScope.PERSONAL,
            required_review_status=DocumentReviewStatus.NOT_REQUIRED,
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
    )


@router.post(
    "/{knowledge_base_id}/documents/{document_id}/parse-tasks",
    response_model=DocumentTaskRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_personal_document_parse_task_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
            scope=KnowledgeBaseScope.PERSONAL,
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
async def create_personal_document_chunk_task_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
            scope=KnowledgeBaseScope.PERSONAL,
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
async def create_personal_document_embed_task_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
            scope=KnowledgeBaseScope.PERSONAL,
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
async def create_personal_document_index_task_endpoint(
    knowledge_base_id: int,
    document_id: int,
    db: DBSession,
    current_user: CurrentUser,
) -> DocumentTaskRead:
    knowledge_base = _get_owned_knowledge_base_or_404(
        db,
        knowledge_base_id=knowledge_base_id,
        user_id=current_user.id,
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
            scope=KnowledgeBaseScope.PERSONAL,
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
