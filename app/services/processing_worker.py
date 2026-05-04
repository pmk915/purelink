from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import BASE_DIR, get_settings
from app.db.session import SessionLocal
from app.models.enums import ProcessingJobStatus
from app.models.enums import DocumentProcessingStatus, ProcessingJobTrigger, ProcessingJobType
from app.models.document import Document
from app.models.processing_job import ProcessingJob
from app.services.document import update_document_processing_status
from app.services.document_processing import (
    DocumentProcessingError,
    ProcessedDocumentResult,
    process_document,
)
from app.services.document_indexing import (
    DocumentIndexingError,
    build_document_index,
    resolve_indexing_roots,
)
from app.services.processing_job import (
    acquire_processing_job,
    can_retry_processing_job,
    create_processing_job_for_document,
    fail_timed_out_processing_jobs,
    get_active_processing_job_for_document,
    get_processing_job,
    infer_processing_job_trigger,
)
from app.services.processing_queue import enqueue_processing_job
from app.services.processing_job import (
    mark_processing_job_failed,
    mark_processing_job_for_retry,
    mark_processing_job_step,
    mark_processing_job_succeeded,
)
from app.services.document import resolve_upload_root


logger = logging.getLogger("purelink.processing")

REDIS_PROCESSING_WORKER_NAME = "redis-document-processing-worker"
REDIS_INDEXING_WORKER_NAME = "redis-document-indexing-worker"


def open_processing_session() -> Session:
    return SessionLocal()


def submit_processing_job(
    *,
    job: ProcessingJob,
) -> str:
    return enqueue_processing_job(job=job)


def _submit_processing_job_best_effort(*, job: ProcessingJob) -> bool:
    try:
        submit_processing_job(job=job)
    except Exception:
        logger.exception(
            "processing job enqueue failed job_id=%s document_id=%s job_type=%s status=%s",
            job.id,
            job.document_id,
            job.job_type,
            job.status,
        )
        return False
    return True


def create_and_submit_processing_job(
    db: Session,
    *,
    document: Document,
    triggered_by_id: int,
    trigger_type: ProcessingJobTrigger | None = None,
) -> ProcessingJob:
    selected_trigger = trigger_type or infer_processing_job_trigger(document=document)
    job = create_processing_job_for_document(
        db,
        document=document,
        triggered_by_id=triggered_by_id,
        trigger_type=selected_trigger,
    )
    if not _submit_processing_job_best_effort(job=job):
        raise RuntimeError(
            "Processing job was created but could not be submitted to Redis. "
            "It remains queued and will be retried by worker recovery."
        )

    return job


def create_and_submit_indexing_job(
    db: Session,
    *,
    document: Document,
    triggered_by_id: int,
    trigger_type: ProcessingJobTrigger = ProcessingJobTrigger.INDEX,
) -> ProcessingJob:
    active_job = get_active_processing_job_for_document(
        db,
        document_id=document.id,
        job_type=ProcessingJobType.DOCUMENT_INDEX,
    )
    if active_job is not None:
        if active_job.status == ProcessingJobStatus.QUEUED:
            _submit_processing_job_best_effort(job=active_job)
        return active_job

    job = create_processing_job_for_document(
        db,
        document=document,
        triggered_by_id=triggered_by_id,
        trigger_type=trigger_type,
        job_type=ProcessingJobType.DOCUMENT_INDEX,
    )
    if not _submit_processing_job_best_effort(job=job):
        raise RuntimeError(
            "Indexing job was created but could not be submitted to Redis. "
            "It remains queued and will be retried by worker recovery."
        )

    return job


def ensure_indexing_job_submitted(
    db: Session,
    *,
    document: Document,
    triggered_by_id: int,
) -> tuple[ProcessingJob, bool, bool]:
    active_job = get_active_processing_job_for_document(
        db,
        document_id=document.id,
        job_type=ProcessingJobType.DOCUMENT_INDEX,
    )
    if active_job is not None:
        enqueue_result = False
        if active_job.status == ProcessingJobStatus.QUEUED:
            enqueue_result = _submit_processing_job_best_effort(job=active_job)
        return active_job, False, enqueue_result

    job = create_processing_job_for_document(
        db,
        document=document,
        triggered_by_id=triggered_by_id,
        trigger_type=ProcessingJobTrigger.INDEX,
        job_type=ProcessingJobType.DOCUMENT_INDEX,
    )
    enqueue_result = _submit_processing_job_best_effort(job=job)
    return job, True, enqueue_result


def requeue_queued_processing_jobs() -> int:
    db = open_processing_session()
    try:
        queued_jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.status == ProcessingJobStatus.QUEUED)
                .order_by(ProcessingJob.id.asc())
            )
        )
        for job in queued_jobs:
            submit_processing_job(job=job)
        return len(queued_jobs)
    finally:
        db.close()


def execute_processing_job(
    *,
    job_id: int,
    worker_name: str = REDIS_PROCESSING_WORKER_NAME,
) -> None:
    db = open_processing_session()
    try:
        settings = get_settings()
        fail_timed_out_processing_jobs(
            db,
            timeout_seconds=settings.processing_job_timeout_seconds,
        )
        job = get_processing_job(db, job_id=job_id)
        if job is None:
            logger.warning("processing job not found job_id=%s", job_id)
            return
        if job.status in {
            ProcessingJobStatus.SUCCEEDED,
            ProcessingJobStatus.FAILED,
        }:
            logger.info(
                "processing job already finalized job_id=%s status=%s",
                job.id,
                job.status,
            )
            return
        if job.status != ProcessingJobStatus.QUEUED:
            logger.info(
                "processing job is not claimable job_id=%s status=%s job_type=%s",
                job.id,
                job.status,
                job.job_type,
            )
            return

        claim_worker_name = (
            REDIS_INDEXING_WORKER_NAME
            if job.job_type == ProcessingJobType.DOCUMENT_INDEX
            else worker_name
        )
        job = acquire_processing_job(
            db,
            job_id=job.id,
            worker_name=claim_worker_name,
            timeout_seconds=settings.processing_job_timeout_seconds,
        )
        if job is None:
            logger.info("processing job already claimed job_id=%s", job_id)
            return

        if job.job_type == ProcessingJobType.DOCUMENT_PROCESS:
            upload_root = resolve_upload_root(settings.upload_dir, base_dir=BASE_DIR)

            try:
                run_processing_job_worker(
                    db,
                    job=job,
                    upload_root=upload_root,
                    worker_name=worker_name,
                )
            except DocumentProcessingError:
                logger.info(
                    "processing job did not complete job_id=%s document_id=%s retry_count=%s max_retries=%s "
                    "locked_by=%s current_step=%s error_code=%s duration_ms=%s",
                    job.id,
                    job.document_id,
                    job.retry_count,
                    job.max_retries,
                    job.locked_by,
                    job.current_step,
                    job.error_code,
                    _job_duration_ms(job),
                )
            except Exception as exc:  # pragma: no cover - defensive guard for unexpected worker failures
                db.rollback()
                error_message = "Processing job failed unexpectedly."
                _handle_processing_job_failure(
                    db,
                    job=job,
                    error_message=error_message,
                    error_code="DOCUMENT_PROCESSING_FAILED",
                    mark_document_failed=True,
                )
                logger.exception(
                    "processing job unexpected failure job_id=%s document_id=%s job_type=%s retry_count=%s "
                    "max_retries=%s locked_by=%s current_step=%s error_code=%s duration_ms=%s",
                    job.id,
                    job.document_id,
                    job.job_type,
                    job.retry_count,
                    job.max_retries,
                    job.locked_by,
                    job.current_step,
                    job.error_code,
                    _job_duration_ms(job),
                )
                raise RuntimeError(error_message) from exc
            return

        if job.job_type == ProcessingJobType.DOCUMENT_INDEX:
            chunks_root, vector_root = resolve_indexing_roots(
                chunks_dir=settings.chunks_dir,
                vector_store_dir=settings.vector_store_dir,
                base_dir=BASE_DIR,
            )
            try:
                run_indexing_job_worker(
                    db,
                    job=job,
                    chunks_root=chunks_root,
                    vector_root=vector_root,
                    worker_name=REDIS_INDEXING_WORKER_NAME,
                )
            except DocumentIndexingError:
                logger.info(
                    "indexing job did not complete job_id=%s document_id=%s retry_count=%s max_retries=%s "
                    "locked_by=%s current_step=%s error_code=%s duration_ms=%s",
                    job.id,
                    job.document_id,
                    job.retry_count,
                    job.max_retries,
                    job.locked_by,
                    job.current_step,
                    job.error_code,
                    _job_duration_ms(job),
                )
            except Exception as exc:  # pragma: no cover - defensive guard for unexpected worker failures
                db.rollback()
                error_message = "Indexing job failed unexpectedly."
                _handle_processing_job_failure(
                    db,
                    job=job,
                    error_message=error_message,
                    error_code="DOCUMENT_INDEXING_FAILED",
                    mark_document_failed=False,
                )
                logger.exception(
                    "indexing job unexpected failure job_id=%s document_id=%s job_type=%s retry_count=%s "
                    "max_retries=%s locked_by=%s current_step=%s error_code=%s duration_ms=%s",
                    job.id,
                    job.document_id,
                    job.job_type,
                    job.retry_count,
                    job.max_retries,
                    job.locked_by,
                    job.current_step,
                    job.error_code,
                    _job_duration_ms(job),
                )
                raise RuntimeError(error_message) from exc
            return

        logger.warning("unsupported processing job type job_id=%s job_type=%s", job.id, job.job_type)
        mark_processing_job_failed(
            db,
            job=job,
            error_message="Unsupported processing job type.",
            error_code="UNSUPPORTED_PROCESSING_JOB_TYPE",
        )
    finally:
        db.close()


def run_processing_job_worker(
    db: Session,
    *,
    job: ProcessingJob,
    upload_root,
    worker_name: str = REDIS_PROCESSING_WORKER_NAME,
) -> ProcessedDocumentResult:
    started_at = datetime.now(UTC)
    try:
        result = process_document(
            db,
            document=job.document,
            upload_root=upload_root,
            progress_callback=lambda step: mark_processing_job_step(
                db,
                job=job,
                current_step=step,
            ),
        )
    except DocumentProcessingError as exc:
        _handle_processing_job_failure(
            db,
            job=job,
            error_message=str(exc),
            error_code=getattr(exc, "error_code", None),
            mark_document_failed=True,
        )
        raise

    mark_processing_job_succeeded(
        db,
        job=job,
    )
    indexing_job_id = None
    indexing_job_enqueued = False
    indexing_job_created = False
    try:
        index_job, indexing_job_created, indexing_job_enqueued = ensure_indexing_job_submitted(
            db,
            document=job.document,
            triggered_by_id=job.triggered_by_id,
        )
        indexing_job_id = index_job.id
    except Exception:
        logger.exception(
            "failed to create or submit automatic indexing job document_id=%s",
            job.document_id,
        )

    logger.info(
        "processing job succeeded job_id=%s document_id=%s job_type=%s retry_count=%s max_retries=%s "
        "locked_by=%s current_step=%s duration_ms=%s chunk_count=%s citation_unit_count=%s "
        "created_index_job_id=%s created_index_job=%s enqueue_index_job_result=%s",
        job.id,
        job.document_id,
        job.job_type,
        job.retry_count,
        job.max_retries,
        job.locked_by or worker_name,
        job.current_step,
        int((datetime.now(UTC) - started_at).total_seconds() * 1000),
        result.chunk_count,
        result.citation_unit_count,
        indexing_job_id,
        indexing_job_created,
        indexing_job_enqueued,
    )
    return result


def run_indexing_job_worker(
    db: Session,
    *,
    job: ProcessingJob,
    chunks_root,
    vector_root,
    worker_name: str = REDIS_INDEXING_WORKER_NAME,
):
    started_at = datetime.now(UTC)
    try:
        result = build_document_index(
            db,
            document=job.document,
            chunks_root=chunks_root,
            vector_root=vector_root,
            progress_callback=lambda step: mark_processing_job_step(
                db,
                job=job,
                current_step=step,
            ),
        )
    except DocumentIndexingError as exc:
        _handle_processing_job_failure(
            db,
            job=job,
            error_message=str(exc),
            error_code=getattr(exc, "error_code", None) or "DOCUMENT_INDEXING_FAILED",
            mark_document_failed=False,
        )
        raise

    mark_processing_job_succeeded(
        db,
        job=job,
    )
    logger.info(
        "indexing job succeeded job_id=%s document_id=%s job_type=%s retry_count=%s max_retries=%s "
        "locked_by=%s current_step=%s duration_ms=%s chunk_count=%s embedding_provider=%s index_path=%s final_status=%s",
        job.id,
        job.document_id,
        job.job_type,
        job.retry_count,
        job.max_retries,
        job.locked_by or worker_name,
        job.current_step,
        int((datetime.now(UTC) - started_at).total_seconds() * 1000),
        result.embedded_chunk_count,
        result.embedding_provider,
        result.index_path,
        ProcessingJobStatus.SUCCEEDED,
    )
    return result


def _handle_processing_job_failure(
    db: Session,
    *,
    job: ProcessingJob,
    error_message: str,
    error_code: str | None,
    mark_document_failed: bool,
) -> None:
    if can_retry_processing_job(job=job, error_code=error_code):
        retried_job = mark_processing_job_for_retry(
            db,
            job=job,
            error_message=error_message,
            error_code=error_code,
        )
        if mark_document_failed and retried_job.document is not None:
            update_document_processing_status(
                db,
                document=retried_job.document,
                processing_status=DocumentProcessingStatus.PROCESSING,
                error_message=None,
                processed_at=None,
            )
        submit_processing_job(job=retried_job)
        logger.warning(
            "processing job scheduled for retry job_id=%s document_id=%s job_type=%s retry_count=%s "
            "max_retries=%s locked_by=%s current_step=%s error_code=%s duration_ms=%s",
            retried_job.id,
            retried_job.document_id,
            retried_job.job_type,
            retried_job.retry_count,
            retried_job.max_retries,
            retried_job.locked_by,
            retried_job.current_step,
            retried_job.error_code,
            _job_duration_ms(retried_job),
        )
        return

    mark_processing_job_failed(
        db,
        job=job,
        error_message=error_message,
        error_code=error_code,
    )
    if mark_document_failed and job.document is not None:
        update_document_processing_status(
            db,
            document=job.document,
            processing_status=DocumentProcessingStatus.FAILED,
            error_message=error_message,
            processed_at=None,
        )


def _job_duration_ms(job: ProcessingJob) -> int | None:
    if job.started_at is None:
        return None
    started_at = job.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    finished_at = job.finished_at or datetime.now(UTC)
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=UTC)
    return int((finished_at - started_at).total_seconds() * 1000)
