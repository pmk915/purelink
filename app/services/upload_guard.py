from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"
UPLOAD_TOO_LARGE = "UPLOAD_TOO_LARGE"
FILE_TOO_LARGE = UPLOAD_TOO_LARGE
UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
VALIDATION_ERROR = "VALIDATION_ERROR"
TOO_MANY_ACTIVE_JOBS = "TOO_MANY_ACTIVE_JOBS"

READ_CHUNK_SIZE = 1024 * 1024
OCTET_STREAM = "application/octet-stream"
UPLOAD_FORMAT_LABELS = {
    ".pdf": "PDF",
    ".docx": "DOCX",
    ".md": "Markdown",
    ".txt": "TXT",
}
EXTENSION_MIME_COMPATIBILITY = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
    ".md": {"text/markdown", "text/plain"},
    ".txt": {"text/plain"},
}


@dataclass(frozen=True, slots=True)
class UploadGuardError(Exception):
    error_code: str
    message: str
    status_code: int
    details: dict[str, int | str | list[str]] | None = None

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class UploadValidationResult:
    filename: str
    content_type: str
    content: bytes
    file_size: int
    max_upload_size_mb: int
    max_upload_size_bytes: int


@dataclass(frozen=True, slots=True)
class UploadConstraints:
    max_upload_size_mb: int
    max_upload_size_bytes: int
    allowed_extensions: tuple[str, ...]
    allowed_mime_types: tuple[str, ...]


def build_upload_constraints(
    *,
    max_upload_size_mb: int,
    allowed_extensions: tuple[str, ...] | list[str] | set[str],
    allowed_mime_types: tuple[str, ...] | list[str] | set[str],
) -> UploadConstraints:
    return UploadConstraints(
        max_upload_size_mb=max_upload_size_mb,
        max_upload_size_bytes=max_upload_size_mb * 1024 * 1024,
        allowed_extensions=tuple(sorted(_normalize_extensions(allowed_extensions))),
        allowed_mime_types=tuple(sorted(_normalize_mime_types(allowed_mime_types))),
    )


async def read_and_validate_upload_file(
    file: Any,
    *,
    max_upload_size_mb: int,
    allowed_extensions: tuple[str, ...] | list[str] | set[str],
    allowed_mime_types: tuple[str, ...] | list[str] | set[str],
) -> UploadValidationResult:
    constraints = build_upload_constraints(
        max_upload_size_mb=max_upload_size_mb,
        allowed_extensions=allowed_extensions,
        allowed_mime_types=allowed_mime_types,
    )
    filename = validate_upload_filename(getattr(file, "filename", None))
    extension = validate_upload_extension(
        filename,
        allowed_extensions=constraints.allowed_extensions,
    )
    content_type = validate_upload_mime_type(
        extension=extension,
        mime_type=getattr(file, "content_type", None),
        allowed_mime_types=constraints.allowed_mime_types,
    )
    content = await _read_upload_content_with_limit(
        file,
        max_upload_size_bytes=constraints.max_upload_size_bytes,
        max_upload_size_mb=constraints.max_upload_size_mb,
    )
    if not content:
        raise UploadGuardError(
            error_code=VALIDATION_ERROR,
            message="Uploaded file is empty.",
            status_code=400,
        )

    return UploadValidationResult(
        filename=filename,
        content_type=content_type,
        content=content,
        file_size=len(content),
        max_upload_size_mb=constraints.max_upload_size_mb,
        max_upload_size_bytes=constraints.max_upload_size_bytes,
    )


def validate_upload_filename(filename: str | None) -> str:
    normalized = (filename or "").strip()
    if (
        not normalized
        or "/" in normalized
        or "\\" in normalized
        or "\x00" in normalized
        or len(normalized) > 255
    ):
        raise UploadGuardError(
            error_code=VALIDATION_ERROR,
            message="Invalid file name.",
            status_code=400,
        )
    return normalized


def validate_upload_extension(
    filename: str,
    *,
    allowed_extensions: tuple[str, ...] | list[str] | set[str],
) -> str:
    extension = Path(filename).suffix.lower()
    normalized_allowed = _normalize_extensions(allowed_extensions)
    if extension in normalized_allowed:
        return extension

    raise UploadGuardError(
        error_code=UNSUPPORTED_FILE_TYPE,
        message=f"Unsupported file type. Allowed: {_allowed_format_label(normalized_allowed)}.",
        status_code=415,
        details={"allowed_extensions": sorted(normalized_allowed)},
    )


def validate_upload_mime_type(
    *,
    extension: str,
    mime_type: str | None,
    allowed_mime_types: tuple[str, ...] | list[str] | set[str],
) -> str:
    normalized_mime_type = (mime_type or "").split(";", 1)[0].strip().lower()
    if not normalized_mime_type or normalized_mime_type == OCTET_STREAM:
        return normalized_mime_type or OCTET_STREAM

    normalized_allowed = _normalize_mime_types(allowed_mime_types)
    compatible_mime_types = EXTENSION_MIME_COMPATIBILITY.get(extension, set())
    if (
        normalized_mime_type in normalized_allowed
        and normalized_mime_type in compatible_mime_types
    ):
        return normalized_mime_type

    raise UploadGuardError(
        error_code=UNSUPPORTED_FILE_TYPE,
        message=(
            "Unsupported file type. "
            f"Allowed: {_allowed_format_label(set(UPLOAD_FORMAT_LABELS))}."
        ),
        status_code=415,
        details={
            "content_type": normalized_mime_type,
            "allowed_mime_types": sorted(normalized_allowed),
        },
    )


def validate_upload_size(
    *,
    file_size: int,
    max_upload_size_mb: int,
) -> None:
    max_bytes = max_upload_size_mb * 1024 * 1024
    if file_size <= max_bytes:
        return

    raise UploadGuardError(
        error_code=UPLOAD_TOO_LARGE,
        message=f"Uploaded file exceeds the maximum size of {max_upload_size_mb} MB.",
        status_code=413,
        details={
            "max_upload_size_mb": max_upload_size_mb,
            "max_upload_size_bytes": max_bytes,
        },
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


def build_upload_error_detail(
    *,
    error_code: str,
    message: str,
    details: dict[str, int | str | list[str]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "error_code": error_code,
        "message": message,
    }
    if details:
        payload.update(details)
    return payload


async def _read_upload_content_with_limit(
    file: Any,
    *,
    max_upload_size_bytes: int,
    max_upload_size_mb: int,
) -> bytes:
    chunks: list[bytes] = []
    total_size = 0
    while True:
        chunk = await file.read(READ_CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_upload_size_bytes:
            raise UploadGuardError(
                error_code=UPLOAD_TOO_LARGE,
                message=f"Uploaded file exceeds the maximum size of {max_upload_size_mb} MB.",
                status_code=413,
                details={
                    "max_upload_size_mb": max_upload_size_mb,
                    "max_upload_size_bytes": max_upload_size_bytes,
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _normalize_extensions(values: tuple[str, ...] | list[str] | set[str]) -> set[str]:
    return {
        value.strip().lower() if value.strip().startswith(".") else f".{value.strip().lower()}"
        for value in values
        if value and value.strip()
    }


def _normalize_mime_types(values: tuple[str, ...] | list[str] | set[str]) -> set[str]:
    return {value.strip().lower() for value in values if value and value.strip()}


def _allowed_format_label(allowed_extensions: set[str]) -> str:
    labels = [
        UPLOAD_FORMAT_LABELS.get(extension, extension.lstrip(".").upper())
        for extension in sorted(allowed_extensions)
    ]
    return ", ".join(labels)
