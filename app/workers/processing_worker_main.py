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

    recovered = requeue_inflight_processing_job_messages()
    logger.info("processing worker recovered %s inflight tasks", recovered)

    while True:
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
