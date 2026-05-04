from __future__ import annotations

import logging
import time

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services import processing_worker
from app.services.processing_queue import (
    RedisError,
    acknowledge_processing_job_message,
    requeue_inflight_processing_job_messages,
    reserve_processing_job_message,
)


logger = logging.getLogger("purelink.worker.processing")


def run_processing_worker_loop() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    recovery_interval_seconds = max(1, settings.processing_queue_recovery_interval_seconds)

    while True:
        try:
            recovered = requeue_inflight_processing_job_messages()
            resubmitted = processing_worker.requeue_queued_processing_jobs()
            logger.info(
                "processing worker recovered %s inflight tasks and resubmitted %s queued jobs",
                recovered,
                resubmitted,
            )
            break
        except RedisError:
            logger.exception("processing worker failed during startup queue recovery")
            time.sleep(1)

    last_queue_recovery_at = time.monotonic()
    while True:
        now = time.monotonic()
        if now - last_queue_recovery_at >= recovery_interval_seconds:
            try:
                resubmitted = processing_worker.requeue_queued_processing_jobs()
                if resubmitted:
                    logger.info(
                        "processing worker periodic queued recovery resubmitted %s queued jobs",
                        resubmitted,
                    )
            except RedisError:
                logger.exception("processing worker failed during periodic queued recovery")
            last_queue_recovery_at = now

        try:
            message = reserve_processing_job_message()
        except RedisError:
            logger.exception("processing worker failed to reserve a Redis task")
            time.sleep(1)
            continue

        if message is None:
            continue

        try:
            processing_worker.execute_processing_job(
                job_id=message.job_id,
                worker_name=processing_worker.REDIS_PROCESSING_WORKER_NAME,
            )
        finally:
            try:
                acknowledge_processing_job_message(raw_payload=message.raw_payload)
            except RedisError:
                logger.exception(
                    "processing worker failed to acknowledge task job_id=%s",
                    message.job_id,
                )


def main() -> None:
    run_processing_worker_loop()


if __name__ == "__main__":
    main()
