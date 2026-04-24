from __future__ import annotations

import logging

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
    create_processing_job_for_document,
    get_processing_job,
    infer_processing_job_trigger,
)
from app.services.processing_queue import enqueue_processing_job
from app.services.processing_job import (
    mark_processing_job_failed,
    mark_processing_job_started,
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
    try:
        submit_processing_job(
            job=job,
        )
    except Exception as exc:
        error_message = "Unable to submit processing job."
        mark_processing_job_failed(
            db,
            job=job,
            error_message=error_message,
        )
        update_document_processing_status(
            db,
            document=document,
            processing_status=DocumentProcessingStatus.FAILED,
            error_message=error_message,
            processed_at=None,
        )
        raise RuntimeError(error_message) from exc

    return job


def create_and_submit_indexing_job(
    db: Session,
    *,
    document: Document,
    triggered_by_id: int,
    trigger_type: ProcessingJobTrigger = ProcessingJobTrigger.INDEX,
) -> ProcessingJob:
    job = create_processing_job_for_document(
        db,
        document=document,
        triggered_by_id=triggered_by_id,
        trigger_type=trigger_type,
        job_type=ProcessingJobType.DOCUMENT_INDEX,
    )
    try:
        submit_processing_job(
            job=job,
        )
    except Exception as exc:
        error_message = "Unable to submit indexing job."
        mark_processing_job_failed(
            db,
            job=job,
            error_message=error_message,
        )
        raise RuntimeError(error_message) from exc

    return job


def execute_processing_job(
    *,
    job_id: int,
    worker_name: str = REDIS_PROCESSING_WORKER_NAME,
) -> None:
    db = open_processing_session()
    try:
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

        if job.job_type == ProcessingJobType.DOCUMENT_PROCESS:
            settings = get_settings()
            upload_root = resolve_upload_root(settings.upload_dir, base_dir=BASE_DIR)

            try:
                run_processing_job_worker(
                    db,
                    job=job,
                    upload_root=upload_root,
                    worker_name=worker_name,
                )
            except DocumentProcessingError:
                logger.info("processing job failed job_id=%s", job_id)
            except Exception as exc:  # pragma: no cover - defensive guard for unexpected worker failures
                logger.exception("processing job unexpected failure job_id=%s", job_id)
                db.rollback()
                error_message = "Processing job failed unexpectedly."
                mark_processing_job_failed(
                    db,
                    job=job,
                    error_message=error_message,
                )
                if job.document is not None:
                    update_document_processing_status(
                        db,
                        document=job.document,
                        processing_status=DocumentProcessingStatus.FAILED,
                        error_message=error_message,
                        processed_at=None,
                    )
                raise RuntimeError(error_message) from exc
            return

        if job.job_type == ProcessingJobType.DOCUMENT_INDEX:
            settings = get_settings()
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
                logger.info("indexing job failed job_id=%s", job_id)
            except Exception as exc:  # pragma: no cover - defensive guard for unexpected worker failures
                logger.exception("indexing job unexpected failure job_id=%s", job_id)
                db.rollback()
                error_message = "Indexing job failed unexpectedly."
                mark_processing_job_failed(
                    db,
                    job=job,
                    error_message=error_message,
                )
                raise RuntimeError(error_message) from exc
            return

        logger.warning("unsupported processing job type job_id=%s job_type=%s", job.id, job.job_type)
        mark_processing_job_failed(
            db,
            job=job,
            error_message="Unsupported processing job type.",
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
    mark_processing_job_started(
        db,
        job=job,
        worker_name=worker_name,
    )
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
        mark_processing_job_failed(
            db,
            job=job,
            error_message=str(exc),
        )
        raise

    mark_processing_job_succeeded(
        db,
        job=job,
    )
    try:
        create_and_submit_indexing_job(
            db,
            document=job.document,
            triggered_by_id=job.triggered_by_id,
        )
    except Exception:
        logger.exception(
            "failed to submit automatic indexing job document_id=%s",
            job.document_id,
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
    mark_processing_job_started(
        db,
        job=job,
        worker_name=worker_name,
    )
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
        mark_processing_job_failed(
            db,
            job=job,
            error_message=str(exc),
        )
        raise

    mark_processing_job_succeeded(
        db,
        job=job,
    )
    return result
