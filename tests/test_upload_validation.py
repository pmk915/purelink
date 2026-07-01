from __future__ import annotations

import pytest

from app.services.upload_guard import (
    UNSUPPORTED_FILE_TYPE,
    UPLOAD_TOO_LARGE,
    VALIDATION_ERROR,
    UploadGuardError,
    read_and_validate_upload_file,
)


ALLOWED_EXTENSIONS = (".pdf", ".docx", ".md", ".txt")
ALLOWED_MIME_TYPES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/markdown",
    "text/plain",
)


class FakeUploadFile:
    def __init__(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None,
    ) -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._content):
            return b""
        if size < 0:
            size = len(self._content) - self._offset
        start = self._offset
        end = min(len(self._content), start + size)
        self._offset = end
        return self._content[start:end]


def _upload_file(
    filename: str,
    content: bytes,
    content_type: str | None,
) -> FakeUploadFile:
    return FakeUploadFile(
        filename=filename,
        content=content,
        content_type=content_type,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("notes.txt", "text/plain"),
        ("guide.md", "text/markdown"),
        ("report.pdf", "application/pdf"),
        (
            "architecture.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ],
)
async def test_supported_upload_types_are_accepted(
    filename: str,
    content_type: str,
) -> None:
    result = await read_and_validate_upload_file(
        _upload_file(filename, b"valid content", content_type),
        max_upload_size_mb=1,
        allowed_extensions=ALLOWED_EXTENSIONS,
        allowed_mime_types=ALLOWED_MIME_TYPES,
    )

    assert result.filename == filename
    assert result.file_size == len(b"valid content")


@pytest.mark.anyio
async def test_empty_upload_is_rejected() -> None:
    with pytest.raises(UploadGuardError) as exc_info:
        await read_and_validate_upload_file(
            _upload_file("empty.txt", b"", "text/plain"),
            max_upload_size_mb=1,
            allowed_extensions=ALLOWED_EXTENSIONS,
            allowed_mime_types=ALLOWED_MIME_TYPES,
        )

    assert exc_info.value.error_code == VALIDATION_ERROR
    assert exc_info.value.status_code == 400


@pytest.mark.anyio
async def test_too_large_upload_is_rejected_without_large_fixture() -> None:
    with pytest.raises(UploadGuardError) as exc_info:
        await read_and_validate_upload_file(
            _upload_file("too-large.txt", b"x", "text/plain"),
            max_upload_size_mb=0,
            allowed_extensions=ALLOWED_EXTENSIONS,
            allowed_mime_types=ALLOWED_MIME_TYPES,
        )

    assert exc_info.value.error_code == UPLOAD_TOO_LARGE
    assert exc_info.value.status_code == 413
    assert exc_info.value.details == {
        "max_upload_size_mb": 0,
        "max_upload_size_bytes": 0,
    }


@pytest.mark.anyio
async def test_unsupported_extension_is_rejected() -> None:
    with pytest.raises(UploadGuardError) as exc_info:
        await read_and_validate_upload_file(
            _upload_file("payload.exe", b"binary", "application/octet-stream"),
            max_upload_size_mb=1,
            allowed_extensions=ALLOWED_EXTENSIONS,
            allowed_mime_types=ALLOWED_MIME_TYPES,
        )

    assert exc_info.value.error_code == UNSUPPORTED_FILE_TYPE
    assert exc_info.value.status_code == 415


@pytest.mark.anyio
@pytest.mark.parametrize("filename", ["", "   ", "../secret.txt", "folder\\secret.txt", "bad\x00name.txt"])
async def test_invalid_filename_is_rejected(filename: str) -> None:
    with pytest.raises(UploadGuardError) as exc_info:
        await read_and_validate_upload_file(
            _upload_file(filename, b"content", "text/plain"),
            max_upload_size_mb=1,
            allowed_extensions=ALLOWED_EXTENSIONS,
            allowed_mime_types=ALLOWED_MIME_TYPES,
        )

    assert exc_info.value.error_code == VALIDATION_ERROR
    assert exc_info.value.status_code == 400


@pytest.mark.anyio
async def test_dangerous_mismatched_mime_is_rejected() -> None:
    with pytest.raises(UploadGuardError) as exc_info:
        await read_and_validate_upload_file(
            _upload_file("notes.txt", b"content", "image/png"),
            max_upload_size_mb=1,
            allowed_extensions=ALLOWED_EXTENSIONS,
            allowed_mime_types=ALLOWED_MIME_TYPES,
        )

    assert exc_info.value.error_code == UNSUPPORTED_FILE_TYPE
    assert exc_info.value.status_code == 415
