from __future__ import annotations

from dataclasses import dataclass
import json
import logging

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.models.processing_job import ProcessingJob


logger = logging.getLogger("purelink.processing.queue")


@dataclass(frozen=True, slots=True)
class ProcessingQueueMessage:
    job_id: int
    document_id: int
    job_type: str
    raw_payload: str


def open_processing_queue_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def _build_processing_queue_payload(*, job: ProcessingJob) -> str:
    return json.dumps(
        {
            "job_id": job.id,
            "document_id": job.document_id,
            "job_type": job.job_type.value,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def enqueue_processing_job(*, job: ProcessingJob) -> str:
    settings = get_settings()
    payload = _build_processing_queue_payload(job=job)
    client = open_processing_queue_redis()
    client.lpush(settings.processing_queue_key, payload)
    return payload


def reserve_processing_job_message(
    *,
    block_timeout_seconds: int | None = None,
) -> ProcessingQueueMessage | None:
    settings = get_settings()
    client = open_processing_queue_redis()
    timeout_seconds = (
        settings.processing_queue_block_timeout_seconds
        if block_timeout_seconds is None
        else block_timeout_seconds
    )
    raw_payload = client.brpoplpush(
        settings.processing_queue_key,
        settings.processing_inflight_queue_key,
        timeout=timeout_seconds,
    )
    if raw_payload is None:
        return None

    try:
        return _deserialize_processing_queue_message(raw_payload=raw_payload)
    except ValueError:  # pragma: no cover - defensive guard for corrupt queue payloads
        logger.exception("dropping invalid processing queue payload")
        client.lrem(settings.processing_inflight_queue_key, 1, raw_payload)
        return None


def acknowledge_processing_job_message(*, raw_payload: str) -> None:
    settings = get_settings()
    client = open_processing_queue_redis()
    client.lrem(settings.processing_inflight_queue_key, 1, raw_payload)


def requeue_inflight_processing_job_messages() -> int:
    settings = get_settings()
    client = open_processing_queue_redis()
    requeued = 0
    while True:
        raw_payload = client.lmove(
            settings.processing_inflight_queue_key,
            settings.processing_queue_key,
            "RIGHT",
            "RIGHT",
        )
        if raw_payload is None:
            break
        requeued += 1
    return requeued


def _deserialize_processing_queue_message(*, raw_payload: str) -> ProcessingQueueMessage:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard for corrupt queue payloads
        raise ValueError("Processing queue payload is not valid JSON.") from exc

    try:
        job_id = int(payload["job_id"])
        document_id = int(payload["document_id"])
        job_type = str(payload["job_type"])
    except (KeyError, TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
        raise ValueError("Processing queue payload is missing required fields.") from exc

    return ProcessingQueueMessage(
        job_id=job_id,
        document_id=document_id,
        job_type=job_type,
        raw_payload=raw_payload,
    )


__all__ = [
    "ProcessingQueueMessage",
    "RedisError",
    "acknowledge_processing_job_message",
    "enqueue_processing_job",
    "open_processing_queue_redis",
    "requeue_inflight_processing_job_messages",
    "reserve_processing_job_message",
]
