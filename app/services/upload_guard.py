from __future__ import annotations

from dataclasses import dataclass


DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"
FILE_TOO_LARGE = "FILE_TOO_LARGE"
TOO_MANY_ACTIVE_JOBS = "TOO_MANY_ACTIVE_JOBS"


@dataclass(frozen=True, slots=True)
class UploadGuardError(Exception):
    error_code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


def validate_upload_size(
    *,
    file_size: int,
    max_upload_size_mb: int,
) -> None:
    max_bytes = max_upload_size_mb * 1024 * 1024
    if file_size <= max_bytes:
        return

    raise UploadGuardError(
        error_code=FILE_TOO_LARGE,
        message=f"File is larger than the configured {max_upload_size_mb} MB upload limit.",
        status_code=413,
    )


def validate_active_job_limits(
    *,
    active_jobs_for_user: int,
    max_active_jobs_per_user: int,
    active_jobs_for_knowledge_base: int,
    max_active_jobs_per_kb: int,
) -> None:
    if active_jobs_for_user >= max_active_jobs_per_user:
        raise UploadGuardError(
            error_code=TOO_MANY_ACTIVE_JOBS,
            message="You have too many active document preparation jobs. Please try again later.",
            status_code=429,
        )
    if active_jobs_for_knowledge_base >= max_active_jobs_per_kb:
        raise UploadGuardError(
            error_code=TOO_MANY_ACTIVE_JOBS,
            message="This knowledge base has too many active document preparation jobs. Please try again later.",
            status_code=429,
        )


def build_upload_error_detail(*, error_code: str, message: str) -> dict[str, str]:
    return {
        "error_code": error_code,
        "message": message,
    }
