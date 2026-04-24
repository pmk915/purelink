from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
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
    ProcessingJobStatus.RUNNING,
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

UNSET = object()


class ActiveProcessingJobExistsError(ValueError):
    pass


class ProcessingJobEligibilityError(ValueError):
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


def get_active_processing_job_for_document(
    db: Session,
    *,
    document_id: int,
) -> ProcessingJob | None:
    statement = (
        select(ProcessingJob)
        .where(
            ProcessingJob.document_id == document_id,
            ProcessingJob.status.in_(ACTIVE_PROCESSING_JOB_STATUSES),
        )
        .order_by(ProcessingJob.id.desc())
    )
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
    worker_name: str | None | object = UNSET,
    error_message: str | None | object = UNSET,
    started_at: datetime | None | object = UNSET,
    finished_at: datetime | None | object = UNSET,
) -> ProcessingJob:
    if status is not UNSET:
        job.status = status
    if current_step is not UNSET:
        job.current_step = current_step
    if worker_name is not UNSET:
        job.worker_name = worker_name
    if error_message is not UNSET:
        job.error_message = error_message
    if started_at is not UNSET:
        job.started_at = started_at
    if finished_at is not UNSET:
        job.finished_at = finished_at
    db.commit()
    db.refresh(job)
    return job


def mark_processing_job_started(
    db: Session,
    *,
    job: ProcessingJob,
    worker_name: str,
) -> ProcessingJob:
    return update_processing_job(
        db,
        job=job,
        status=ProcessingJobStatus.RUNNING,
        current_step=PROCESSING_STEP_RESOLVE_SOURCE,
        worker_name=worker_name,
        error_message=None,
        started_at=datetime.now(UTC),
        finished_at=None,
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
        error_message=None,
        finished_at=datetime.now(UTC),
    )


def mark_processing_job_failed(
    db: Session,
    *,
    job: ProcessingJob,
    error_message: str,
) -> ProcessingJob:
    return update_processing_job(
        db,
        job=job,
        status=ProcessingJobStatus.FAILED,
        error_message=error_message,
        finished_at=datetime.now(UTC),
    )
