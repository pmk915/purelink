from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pathlib import Path

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.models.document import Document
from app.models.enums import (
    DocumentProcessingStatus,
    ProcessingJobStatus,
    ProcessingJobTrigger,
    ProcessingJobType,
)
from app.models.processing_job import ProcessingJob


ACTIVE_PROCESSING_JOB_STATUSES = (
    ProcessingJobStatus.QUEUED,
    ProcessingJobStatus.PROCESSING,
    ProcessingJobStatus.RETRYING,
)
PROCESSING_STEP_QUEUED = "queued"
PROCESSING_STEP_RESOLVE_SOURCE = "resolve_source"
PROCESSING_STEP_EXTRACT_TEXT = "extract_text"
PROCESSING_STEP_CHUNK_CONTENT = "chunk_content"
PROCESSING_STEP_PERSIST_CHUNKS = "persist_chunks"
PROCESSING_STEP_FINALIZE_DOCUMENT = "finalize_document"
PROCESSING_STEP_COMPLETED = "completed"
INDEXING_STEP_LOAD_CHUNKS = "load_chunks"
INDEXING_STEP_BUILD_EMBEDDINGS = "build_embeddings"
INDEXING_STEP_WRITE_INDEX = "write_index"
INDEXING_STEP_FINALIZE_INDEX = "finalize_index"
JOB_TIMEOUT_ERROR_CODE = "JOB_TIMEOUT"

NON_RETRYABLE_PROCESSING_ERROR_CODES = {
    "UNSUPPORTED_FILE_TYPE",
    "FEATURE_NOT_ENABLED",
    "OCR_PROVIDER_UNAVAILABLE",
    "OCR_NO_TEXT_FOUND",
    "PDF_TEXT_GARBLED",
    "PDF_TEXT_EXTRACTION_FAILED",
    "TEXT_QUALITY_TOO_LOW",
    "BINARY_LIKE_TEXT",
    "EMBEDDING_PROVIDER_NOT_INSTALLED",
}
RETRYABLE_PROCESSING_ERROR_CODES = {
    "CHUNK_PERSIST_FAILED",
    "DOCUMENT_PROCESSING_FAILED",
    "TEMPORARY_PROCESSING_ERROR",
}

UNSET = object()


class ActiveProcessingJobExistsError(ValueError):
    pass


class ProcessingJobEligibilityError(ValueError):
    pass


class ProcessingJobSourceMissingError(ValueError):
    pass


def infer_processing_job_trigger(*, document: Document) -> ProcessingJobTrigger:
    if document.processing_status == DocumentProcessingStatus.FAILED:
        return ProcessingJobTrigger.RETRY
    if document.processing_status in {
        DocumentProcessingStatus.READY,
        DocumentProcessingStatus.INDEXED,
        DocumentProcessingStatus.PARSED,
    }:
        return ProcessingJobTrigger.REPROCESS
    return ProcessingJobTrigger.PROCESS


def ensure_document_can_start_processing_job(
    *,
    document: Document,
    trigger_type: ProcessingJobTrigger,
    job_type: ProcessingJobType,
) -> None:
    if job_type == ProcessingJobType.DOCUMENT_INDEX:
        if trigger_type != ProcessingJobTrigger.INDEX:
            raise ProcessingJobEligibilityError("Unsupported indexing trigger.")
        if document.processing_status not in {
            DocumentProcessingStatus.READY,
            DocumentProcessingStatus.INDEXED,
            DocumentProcessingStatus.PARSED,
        }:
            raise ProcessingJobEligibilityError("Document must be ready or chunked before indexing.")
        return

    if job_type != ProcessingJobType.DOCUMENT_PROCESS:
        raise ProcessingJobEligibilityError("Unsupported processing job type.")

    if trigger_type == ProcessingJobTrigger.PROCESS:
        if document.processing_status == DocumentProcessingStatus.PROCESSING:
            raise ProcessingJobEligibilityError("Document is already processing.")
        return

    if trigger_type == ProcessingJobTrigger.RETRY:
        if document.processing_status != DocumentProcessingStatus.FAILED:
            raise ProcessingJobEligibilityError("Only failed documents can be retried.")
        return

    if trigger_type == ProcessingJobTrigger.REPROCESS:
        if document.processing_status not in {
            DocumentProcessingStatus.READY,
            DocumentProcessingStatus.INDEXED,
            DocumentProcessingStatus.PARSED,
        }:
            raise ProcessingJobEligibilityError("Only processed documents can be reprocessed.")
        return

    raise ProcessingJobEligibilityError("Unsupported processing trigger.")


def get_processing_job(
    db: Session,
    *,
    job_id: int,
) -> ProcessingJob | None:
    statement = (
        select(ProcessingJob)
        .options(
            selectinload(ProcessingJob.document).selectinload(Document.knowledge_base),
        )
        .where(ProcessingJob.id == job_id)
    )
    return db.scalar(statement)


def list_processing_jobs_for_document(
    db: Session,
    *,
    document_id: int,
) -> list[ProcessingJob]:
    statement = (
        select(ProcessingJob)
        .where(ProcessingJob.document_id == document_id)
        .order_by(ProcessingJob.id.desc())
    )
    return list(db.scalars(statement))


def list_processing_jobs_for_knowledge_base(
    db: Session,
    *,
    knowledge_base_id: int,
    status_filter: ProcessingJobStatus | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ProcessingJob]:
    statement = (
        select(ProcessingJob)
        .join(Document, Document.id == ProcessingJob.document_id)
        .options(selectinload(ProcessingJob.document))
        .where(Document.knowledge_base_id == knowledge_base_id)
        .order_by(ProcessingJob.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter is not None:
        statement = statement.where(ProcessingJob.status == status_filter)
    normalized_search = (search or "").strip()
    if normalized_search:
        statement = statement.where(Document.original_filename.ilike(f"%{normalized_search}%"))
    return list(db.scalars(statement))


def count_processing_jobs_for_knowledge_base(
    db: Session,
    *,
    knowledge_base_id: int,
    status_filter: ProcessingJobStatus | None = None,
    search: str | None = None,
) -> int:
    statement = (
        select(func.count(ProcessingJob.id))
        .join(Document, Document.id == ProcessingJob.document_id)
        .where(Document.knowledge_base_id == knowledge_base_id)
    )
    if status_filter is not None:
        statement = statement.where(ProcessingJob.status == status_filter)
    normalized_search = (search or "").strip()
    if normalized_search:
        statement = statement.where(Document.original_filename.ilike(f"%{normalized_search}%"))
    return int(db.scalar(statement) or 0)


def count_processing_jobs_by_status_for_knowledge_base(
    db: Session,
    *,
    knowledge_base_id: int,
) -> dict[ProcessingJobStatus, int]:
    statement = (
        select(ProcessingJob.status, func.count(ProcessingJob.id))
        .join(Document, Document.id == ProcessingJob.document_id)
        .where(Document.knowledge_base_id == knowledge_base_id)
        .group_by(ProcessingJob.status)
    )
    return {status: int(count) for status, count in db.execute(statement)}


def get_active_processing_job_for_document(
    db: Session,
    *,
    document_id: int,
    job_type: ProcessingJobType | None = None,
) -> ProcessingJob | None:
    statement = select(ProcessingJob).where(
        ProcessingJob.document_id == document_id,
        ProcessingJob.status.in_(ACTIVE_PROCESSING_JOB_STATUSES),
    )
    if job_type is not None:
        statement = statement.where(ProcessingJob.job_type == job_type)
    statement = statement.order_by(ProcessingJob.id.desc())
    return db.scalar(statement)


def get_latest_processing_job_for_document(
    db: Session,
    *,
    document_id: int,
    job_type: ProcessingJobType | None = None,
) -> ProcessingJob | None:
    statement = select(ProcessingJob).where(ProcessingJob.document_id == document_id)
    if job_type is not None:
        statement = statement.where(ProcessingJob.job_type == job_type)
    statement = statement.order_by(ProcessingJob.id.desc())
    return db.scalar(statement)


def count_active_processing_jobs_for_user(
    db: Session,
    *,
    user_id: int,
) -> int:
    statement = select(func.count(ProcessingJob.id)).where(
        ProcessingJob.triggered_by_id == user_id,
        ProcessingJob.status.in_(ACTIVE_PROCESSING_JOB_STATUSES),
    )
    return int(db.scalar(statement) or 0)


def count_active_processing_jobs_for_knowledge_base(
    db: Session,
    *,
    knowledge_base_id: int,
) -> int:
    statement = (
        select(func.count(ProcessingJob.id))
        .join(Document, Document.id == ProcessingJob.document_id)
        .where(
            Document.knowledge_base_id == knowledge_base_id,
            ProcessingJob.status.in_(ACTIVE_PROCESSING_JOB_STATUSES),
        )
    )
    return int(db.scalar(statement) or 0)


def create_processing_job_for_document(
    db: Session,
    *,
    document: Document,
    triggered_by_id: int,
    trigger_type: ProcessingJobTrigger,
    job_type: ProcessingJobType = ProcessingJobType.DOCUMENT_PROCESS,
) -> ProcessingJob:
    ensure_document_can_start_processing_job(
        document=document,
        trigger_type=trigger_type,
        job_type=job_type,
    )
    active_job = get_active_processing_job_for_document(
        db,
        document_id=document.id,
        job_type=job_type,
    )
    if active_job is not None:
        raise ActiveProcessingJobExistsError(
            "An active processing job already exists for this document.",
        )

    previous_job = get_latest_processing_job_for_document(
        db,
        document_id=document.id,
        job_type=job_type,
    )
    job = ProcessingJob(
        document_id=document.id,
        triggered_by_id=triggered_by_id,
        previous_job_id=previous_job.id if previous_job is not None else None,
        job_type=job_type,
        trigger_type=trigger_type,
        status=ProcessingJobStatus.QUEUED,
        current_step=PROCESSING_STEP_QUEUED,
        attempt_number=(previous_job.attempt_number + 1) if previous_job is not None else 1,
        worker_name=None,
        error_code=None,
        error_message=None,
        started_at=None,
        finished_at=None,
    )
    if job_type == ProcessingJobType.DOCUMENT_PROCESS:
        document.processing_status = DocumentProcessingStatus.PROCESSING
        document.error_message = None
        document.processed_at = None
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_processing_job(
    db: Session,
    *,
    job: ProcessingJob,
    status: ProcessingJobStatus | object = UNSET,
    current_step: str | None | object = UNSET,
    retry_count: int | object = UNSET,
    max_retries: int | object = UNSET,
    worker_name: str | None | object = UNSET,
    locked_by: str | None | object = UNSET,
    error_code: str | None | object = UNSET,
    error_message: str | None | object = UNSET,
    started_at: datetime | None | object = UNSET,
    finished_at: datetime | None | object = UNSET,
    locked_at: datetime | None | object = UNSET,
    timeout_at: datetime | None | object = UNSET,
) -> ProcessingJob:
    if status is not UNSET:
        job.status = status
    if current_step is not UNSET:
        job.current_step = current_step
    if retry_count is not UNSET:
        job.retry_count = retry_count
    if max_retries is not UNSET:
        job.max_retries = max_retries
    if worker_name is not UNSET:
        job.worker_name = worker_name
    if locked_by is not UNSET:
        job.locked_by = locked_by
    if error_code is not UNSET:
        job.error_code = error_code
    if error_message is not UNSET:
        job.error_message = error_message
    if started_at is not UNSET:
        job.started_at = started_at
    if finished_at is not UNSET:
        job.finished_at = finished_at
    if locked_at is not UNSET:
        job.locked_at = locked_at
    if timeout_at is not UNSET:
        job.timeout_at = timeout_at
    db.commit()
    db.refresh(job)
    return job


def acquire_processing_job(
    db: Session,
    *,
    job_id: int,
    worker_name: str,
    timeout_seconds: int,
) -> ProcessingJob | None:
    now = datetime.now(UTC)
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id == job_id,
            ProcessingJob.status == ProcessingJobStatus.QUEUED,
        )
        .values(
            status=ProcessingJobStatus.PROCESSING,
            current_step=PROCESSING_STEP_RESOLVE_SOURCE,
            worker_name=worker_name,
            locked_by=worker_name,
            locked_at=now,
            timeout_at=now + timedelta(seconds=timeout_seconds),
            error_code=None,
            error_message=None,
            started_at=now,
            finished_at=None,
        ),
    )
    if result.rowcount != 1:
        db.rollback()
        return None

    db.commit()
    return get_processing_job(db, job_id=job_id)


def mark_processing_job_started(
    db: Session,
    *,
    job: ProcessingJob,
    worker_name: str,
) -> ProcessingJob:
    now = datetime.now(UTC)
    return update_processing_job(
        db,
        job=job,
        status=ProcessingJobStatus.PROCESSING,
        current_step=PROCESSING_STEP_RESOLVE_SOURCE,
        worker_name=worker_name,
        locked_by=worker_name,
        error_code=None,
        error_message=None,
        started_at=now,
        finished_at=None,
        locked_at=now,
    )


def mark_processing_job_step(
    db: Session,
    *,
    job: ProcessingJob,
    current_step: str,
) -> ProcessingJob:
    return update_processing_job(
        db,
        job=job,
        current_step=current_step,
    )


def mark_processing_job_succeeded(
    db: Session,
    *,
    job: ProcessingJob,
) -> ProcessingJob:
    return update_processing_job(
        db,
        job=job,
        status=ProcessingJobStatus.SUCCEEDED,
        current_step=PROCESSING_STEP_COMPLETED,
        error_code=None,
        error_message=None,
        finished_at=datetime.now(UTC),
    )


def mark_processing_job_failed(
    db: Session,
    *,
    job: ProcessingJob,
    error_message: str,
    error_code: str | None = None,
) -> ProcessingJob:
    return update_processing_job(
        db,
        job=job,
        status=ProcessingJobStatus.FAILED,
        error_code=error_code,
        error_message=error_message,
        finished_at=datetime.now(UTC),
    )


def is_retryable_processing_error(error_code: str | None) -> bool:
    if error_code in NON_RETRYABLE_PROCESSING_ERROR_CODES:
        return False
    if error_code in RETRYABLE_PROCESSING_ERROR_CODES:
        return True
    return False


def can_retry_processing_job(
    *,
    job: ProcessingJob,
    error_code: str | None,
) -> bool:
    return job.retry_count < job.max_retries and is_retryable_processing_error(error_code)


def can_retry_document_processing_job(
    db: Session,
    *,
    job: ProcessingJob,
    upload_root: Path | None = None,
) -> bool:
    if job.job_type != ProcessingJobType.DOCUMENT_PROCESS:
        return False
    if job.status not in {ProcessingJobStatus.FAILED, ProcessingJobStatus.CANCELLED}:
        return False
    if job.document is None:
        return False
    if job.document.processing_status != DocumentProcessingStatus.FAILED:
        return False
    active_job = get_active_processing_job_for_document(
        db,
        document_id=job.document_id,
        job_type=ProcessingJobType.DOCUMENT_PROCESS,
    )
    if active_job is not None:
        return False
    if upload_root is not None and not (upload_root / job.document.storage_path).exists():
        return False
    return True


def retry_document_processing_job(
    db: Session,
    *,
    document: Document,
    triggered_by_id: int,
    upload_root: Path,
) -> ProcessingJob:
    active_job = get_active_processing_job_for_document(
        db,
        document_id=document.id,
        job_type=ProcessingJobType.DOCUMENT_PROCESS,
    )
    if active_job is not None:
        raise ActiveProcessingJobExistsError(
            "An active processing job already exists for this document.",
        )

    latest_job = get_latest_processing_job_for_document(
        db,
        document_id=document.id,
        job_type=ProcessingJobType.DOCUMENT_PROCESS,
    )
    if latest_job is None or latest_job.status not in {
        ProcessingJobStatus.FAILED,
        ProcessingJobStatus.CANCELLED,
    }:
        raise ProcessingJobEligibilityError(
            "Only failed or cancelled document processing jobs can be retried.",
        )
    source_path = upload_root / document.storage_path
    if not source_path.exists():
        raise ProcessingJobSourceMissingError("Original uploaded file is missing.")

    return create_processing_job_for_document(
        db,
        document=document,
        triggered_by_id=triggered_by_id,
        trigger_type=ProcessingJobTrigger.RETRY,
        job_type=ProcessingJobType.DOCUMENT_PROCESS,
    )


def mark_processing_job_for_retry(
    db: Session,
    *,
    job: ProcessingJob,
    error_message: str,
    error_code: str | None,
) -> ProcessingJob:
    return update_processing_job(
        db,
        job=job,
        status=ProcessingJobStatus.QUEUED,
        current_step=PROCESSING_STEP_QUEUED,
        retry_count=job.retry_count + 1,
        worker_name=None,
        error_code=error_code,
        error_message=error_message,
        started_at=None,
        finished_at=None,
        locked_by=None,
        locked_at=None,
        timeout_at=None,
    )


def fail_timed_out_processing_jobs(
    db: Session,
    *,
    now: datetime | None = None,
    timeout_seconds: int = 1800,
) -> int:
    selected_now = now or datetime.now(UTC)
    locked_before = selected_now - timedelta(seconds=timeout_seconds)
    statement = (
        select(ProcessingJob)
        .options(selectinload(ProcessingJob.document))
        .where(
            ProcessingJob.status == ProcessingJobStatus.PROCESSING,
            or_(
                ProcessingJob.timeout_at <= selected_now,
                ProcessingJob.timeout_at.is_(None)
                & ProcessingJob.locked_at.is_not(None)
                & (ProcessingJob.locked_at <= locked_before),
            ),
        )
    )
    jobs = list(db.scalars(statement))
    for job in jobs:
        mark_processing_job_failed(
            db,
            job=job,
            error_message="Processing job timed out.",
            error_code=JOB_TIMEOUT_ERROR_CODE,
        )
        if job.job_type == ProcessingJobType.DOCUMENT_PROCESS and job.document is not None:
            job.document.processing_status = DocumentProcessingStatus.FAILED
            job.document.error_message = "Processing job timed out."
            job.document.processed_at = None
            db.commit()

    return len(jobs)
