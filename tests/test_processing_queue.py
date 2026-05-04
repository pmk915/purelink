from __future__ import annotations

from datetime import UTC, datetime
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, load_all_models
from app.models.document import Document
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
    ProcessingJobStatus,
    ProcessingJobTrigger,
    ProcessingJobType,
)
from app.models.knowledge_base import KnowledgeBase
from app.models.processing_job import ProcessingJob
from app.models.user import User
from app.schemas.processing_job import ProcessingJobRead
from app.services.processing_job import mark_processing_job_for_retry
from app.services.processing_queue import (
    _build_processing_queue_payload,
    _deserialize_processing_queue_message,
)
from app.services.processing_worker import create_and_submit_indexing_job, requeue_queued_processing_jobs
from app.workers import processing_worker_main


load_all_models()


@pytest.fixture
def session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(bind=engine)
    try:
        yield testing_session_local
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _create_document_with_job(db: Session, *, suffix: str = "1") -> ProcessingJob:
    document, user = _create_document(
        db,
        suffix=suffix,
        processing_status=DocumentProcessingStatus.PROCESSING,
    )

    job = ProcessingJob(
        document_id=document.id,
        triggered_by_id=user.id,
        previous_job_id=None,
        job_type=ProcessingJobType.DOCUMENT_PROCESS,
        trigger_type=ProcessingJobTrigger.PROCESS,
        status=ProcessingJobStatus.QUEUED,
        current_step="queued",
        attempt_number=1,
        retry_count=0,
        max_retries=3,
        worker_name=None,
        locked_by=None,
        error_code=None,
        error_message=None,
        started_at=None,
        finished_at=None,
        locked_at=None,
        timeout_at=None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _create_document(
    db: Session,
    *,
    suffix: str = "1",
    processing_status: DocumentProcessingStatus = DocumentProcessingStatus.READY,
) -> tuple[Document, User]:
    user = User(
        email=f"queue-user-{suffix}@example.com",
        username=f"queue-user-{suffix}",
        hashed_password="hashed",
        is_active=True,
    )
    db.add(user)
    db.flush()

    knowledge_base = KnowledgeBase(
        name="Queue KB",
        scope=KnowledgeBaseScope.PERSONAL,
        owner_id=user.id,
    )
    db.add(knowledge_base)
    db.flush()

    document = Document(
        knowledge_base_id=knowledge_base.id,
        owner_id=user.id,
        submitted_by=user.id,
        filename="queue.txt",
        original_filename=f"queue-{suffix}.txt",
        file_type="text/plain",
        file_size=16,
        storage_path=f"personal/knowledge_base_1/queue-{suffix}.txt",
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=processing_status,
    )
    db.add(document)
    db.flush()
    db.commit()
    db.refresh(document)
    db.refresh(user)
    return document, user


def test_processing_queue_payload_contains_only_job_id(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        job = _create_document_with_job(db)

    payload = _build_processing_queue_payload(job=job)
    assert json.loads(payload) == {"job_id": job.id}


def test_processing_queue_deserializer_accepts_legacy_payload() -> None:
    message = _deserialize_processing_queue_message(
        raw_payload='{"job_id":42,"document_id":7,"job_type":"document_process"}'
    )
    assert message.job_id == 42
    assert message.raw_payload


def test_mark_processing_job_for_retry_resets_locking_state(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        job = _create_document_with_job(db)
        job.status = ProcessingJobStatus.PROCESSING
        job.retry_count = 1
        job.worker_name = "worker-a"
        job.locked_by = "worker-a"
        job.locked_at = datetime.now(UTC)
        job.started_at = datetime.now(UTC)
        job.timeout_at = datetime.now(UTC)
        db.commit()
        db.refresh(job)

        retried = mark_processing_job_for_retry(
            db,
            job=job,
            error_message="temporary failure",
            error_code="TEMPORARY_PROCESSING_ERROR",
        )

    assert retried.status == ProcessingJobStatus.QUEUED
    assert retried.retry_count == 2
    assert retried.worker_name is None
    assert retried.locked_by is None
    assert retried.locked_at is None
    assert retried.started_at is None
    assert retried.timeout_at is None
    assert retried.last_error == "temporary failure"


def test_processing_job_read_exposes_last_error(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        job = _create_document_with_job(db)
        job.error_message = "queue failure"
        db.commit()
        db.refresh(job)

        payload = ProcessingJobRead.model_validate(job)

    assert payload.last_error == "queue failure"


def test_requeue_queued_processing_jobs_resubmits_all_queued_jobs(
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued_job_ids: list[int] = []

    with session_factory() as db:
        job = _create_document_with_job(db, suffix="1")
        second_job = _create_document_with_job(db, suffix="2")
        second_job.status = ProcessingJobStatus.SUCCEEDED
        db.commit()

    monkeypatch.setattr(
        "app.services.processing_worker.open_processing_session",
        lambda: session_factory(),
    )
    monkeypatch.setattr(
        "app.services.processing_worker.submit_processing_job",
        lambda *, job: queued_job_ids.append(job.id) or str(job.id),
    )

    recovered = requeue_queued_processing_jobs()

    assert recovered == 1
    assert queued_job_ids == [job.id]


def test_requeue_queued_processing_jobs_resubmits_queued_index_jobs(
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued_job_ids: list[int] = []

    with session_factory() as db:
        document, user = _create_document(
            db,
            suffix="index",
            processing_status=DocumentProcessingStatus.READY,
        )
        index_job = ProcessingJob(
            document_id=document.id,
            triggered_by_id=user.id,
            previous_job_id=None,
            job_type=ProcessingJobType.DOCUMENT_INDEX,
            trigger_type=ProcessingJobTrigger.INDEX,
            status=ProcessingJobStatus.QUEUED,
            current_step="queued",
            attempt_number=1,
            retry_count=0,
            max_retries=3,
        )
        db.add(index_job)
        db.commit()
        db.refresh(index_job)

    monkeypatch.setattr(
        "app.services.processing_worker.open_processing_session",
        lambda: session_factory(),
    )
    monkeypatch.setattr(
        "app.services.processing_worker.submit_processing_job",
        lambda *, job: queued_job_ids.append(job.id) or str(job.id),
    )

    recovered = requeue_queued_processing_jobs()

    assert recovered == 1
    assert queued_job_ids == [index_job.id]


def test_create_and_submit_indexing_job_leaves_job_queued_when_enqueue_fails(
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as db:
        document, user = _create_document(
            db,
            suffix="enqueue-failure",
            processing_status=DocumentProcessingStatus.READY,
        )

        def _raise_submit_failure(*, job: ProcessingJob) -> str:
            raise RuntimeError("redis unavailable")

        monkeypatch.setattr(
            "app.services.processing_worker.submit_processing_job",
            _raise_submit_failure,
        )

        with pytest.raises(RuntimeError, match="remains queued"):
            create_and_submit_indexing_job(
                db,
                document=document,
                triggered_by_id=user.id,
            )

        queued_index_job = db.scalar(
            select(ProcessingJob)
            .where(
                ProcessingJob.document_id == document.id,
                ProcessingJob.job_type == ProcessingJobType.DOCUMENT_INDEX,
            )
            .order_by(ProcessingJob.id.desc())
        )
        assert queued_index_job is not None
        assert queued_index_job.status == ProcessingJobStatus.QUEUED

        db.refresh(document)
        assert document.processing_status == DocumentProcessingStatus.READY


def test_worker_loop_runs_periodic_queued_job_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StopLoop(RuntimeError):
        pass

    recovery_calls: list[str] = []
    monotonic_values = iter([0.0, 2.0])

    monkeypatch.setattr(
        "app.workers.processing_worker_main.get_settings",
        lambda: SimpleNamespace(
            log_level="INFO",
            processing_queue_recovery_interval_seconds=1,
        ),
    )
    monkeypatch.setattr(
        "app.workers.processing_worker_main.configure_logging",
        lambda _level: None,
    )
    monkeypatch.setattr(
        "app.workers.processing_worker_main.requeue_inflight_processing_job_messages",
        lambda: 0,
    )
    monkeypatch.setattr(
        "app.workers.processing_worker_main.processing_worker.requeue_queued_processing_jobs",
        lambda: recovery_calls.append("requeue") or 1,
    )
    monkeypatch.setattr(
        "app.workers.processing_worker_main.time.monotonic",
        lambda: next(monotonic_values),
    )
    monkeypatch.setattr(
        "app.workers.processing_worker_main.reserve_processing_job_message",
        lambda: (_ for _ in ()).throw(StopLoop("stop")),
    )

    with pytest.raises(StopLoop, match="stop"):
        processing_worker_main.run_processing_worker_loop()

    assert recovery_calls == ["requeue", "requeue"]
