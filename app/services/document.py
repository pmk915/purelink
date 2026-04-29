from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import Document
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.models.knowledge_base import KnowledgeBase


UNSET = object()
UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
FEATURE_NOT_ENABLED = "FEATURE_NOT_ENABLED"
SUPPORTED_DOCUMENT_SUFFIXES = {
    ".txt",
    ".md",
    ".pdf",
}
SUPPORTED_DOCUMENT_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "application/pdf",
}
OCR_DOCUMENT_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
OCR_DOCUMENT_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
MEDIA_DOCUMENT_SUFFIXES = {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".m4v"}
MEDIA_DOCUMENT_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mp4",
    "audio/x-m4a",
    "audio/m4a",
    "video/mp4",
    "video/quicktime",
    "video/x-m4v",
}
SUPPORTED_DOCUMENT_FORMAT_HINT = ".txt, .md, and .pdf"


class DocumentUploadSupportError(ValueError):
    def __init__(self, message: str, *, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def is_supported_document_upload(
    *,
    filename: str,
    mime_type: str | None = None,
) -> bool:
    settings = get_settings()
    allowed_suffixes = set(SUPPORTED_DOCUMENT_SUFFIXES)
    allowed_mime_types = set(SUPPORTED_DOCUMENT_MIME_TYPES)
    if settings.enable_ocr:
        allowed_suffixes.update(OCR_DOCUMENT_SUFFIXES)
        allowed_mime_types.update(OCR_DOCUMENT_MIME_TYPES)
    if settings.enable_media:
        allowed_suffixes.update(MEDIA_DOCUMENT_SUFFIXES)
        allowed_mime_types.update(MEDIA_DOCUMENT_MIME_TYPES)

    suffix = Path(filename).suffix.lower()
    if suffix in allowed_suffixes:
        return True

    normalized_mime_type = (mime_type or "").strip().lower()
    return normalized_mime_type in allowed_mime_types


def ensure_supported_document_upload(
    *,
    filename: str,
    mime_type: str | None = None,
) -> None:
    if is_supported_document_upload(filename=filename, mime_type=mime_type):
        return
    settings = get_settings()
    suffix = Path(filename).suffix.lower()
    if suffix in OCR_DOCUMENT_SUFFIXES and not settings.enable_ocr:
        raise DocumentUploadSupportError(
            "This PureLink Core deployment does not enable image OCR uploads.",
            error_code=FEATURE_NOT_ENABLED,
        )
    if suffix in MEDIA_DOCUMENT_SUFFIXES and not settings.enable_media:
        raise DocumentUploadSupportError(
            "This PureLink Core deployment does not enable audio or video uploads.",
            error_code=FEATURE_NOT_ENABLED,
        )
    raise DocumentUploadSupportError(
        f"Only {SUPPORTED_DOCUMENT_FORMAT_HINT} documents are supported in PureLink Core.",
        error_code=UNSUPPORTED_FILE_TYPE,
    )


def create_document(
    db: Session,
    *,
    knowledge_base_id: int,
    owner_id: int,
    submitted_by: int,
    filename: str,
    original_filename: str,
    file_type: str,
    file_size: int,
    storage_path: str,
    review_status: DocumentReviewStatus,
    processing_status: DocumentProcessingStatus,
    sha256: str | None = None,
) -> Document:
    document = Document(
        knowledge_base_id=knowledge_base_id,
        owner_id=owner_id,
        submitted_by=submitted_by,
        filename=filename,
        original_filename=original_filename,
        file_type=file_type,
        file_size=file_size,
        sha256=sha256,
        storage_path=storage_path,
        review_status=review_status,
        processing_status=processing_status,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def compute_document_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def get_document_by_sha256_for_knowledge_base(
    db: Session,
    *,
    knowledge_base_id: int,
    sha256: str,
) -> Document | None:
    statement = select(Document).where(
        Document.knowledge_base_id == knowledge_base_id,
        Document.sha256 == sha256,
    )
    return db.scalar(statement)


def list_documents_for_knowledge_base(
    db: Session,
    *,
    knowledge_base_id: int,
) -> list[Document]:
    statement = (
        select(Document)
        .where(Document.knowledge_base_id == knowledge_base_id)
        .order_by(Document.created_at.desc(), Document.id.desc())
    )
    return list(db.scalars(statement))


def get_document_for_knowledge_base(
    db: Session,
    *,
    knowledge_base_id: int,
    document_id: int,
) -> Document | None:
    statement = select(Document).where(
        Document.id == document_id,
        Document.knowledge_base_id == knowledge_base_id,
    )
    return db.scalar(statement)


def list_pending_team_documents(
    db: Session,
    *,
    team_id: int,
) -> list[Document]:
    statement = (
        select(Document)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(
            KnowledgeBase.scope == KnowledgeBaseScope.TEAM,
            KnowledgeBase.team_id == team_id,
            Document.review_status == DocumentReviewStatus.PENDING_REVIEW,
        )
        .order_by(Document.created_at.asc(), Document.id.asc())
    )
    return list(db.scalars(statement))


def get_team_document(
    db: Session,
    *,
    team_id: int,
    document_id: int,
) -> Document | None:
    statement = (
        select(Document)
        .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
        .where(
            Document.id == document_id,
            KnowledgeBase.scope == KnowledgeBaseScope.TEAM,
            KnowledgeBase.team_id == team_id,
        )
    )
    return db.scalar(statement)


def approve_document_review(
    db: Session,
    *,
    document: Document,
    reviewed_by: int,
) -> Document:
    document.review_status = DocumentReviewStatus.APPROVED
    document.reviewed_by = reviewed_by
    document.reviewed_at = datetime.now(UTC)
    document.review_comment = None
    db.commit()
    db.refresh(document)
    return document


def reject_document_review(
    db: Session,
    *,
    document: Document,
    reviewed_by: int,
    review_comment: str,
) -> Document:
    document.review_status = DocumentReviewStatus.REJECTED
    document.reviewed_by = reviewed_by
    document.reviewed_at = datetime.now(UTC)
    document.review_comment = review_comment
    db.commit()
    db.refresh(document)
    return document


def update_document_processing_status(
    db: Session,
    *,
    document: Document,
    processing_status: DocumentProcessingStatus,
    error_message: str | None | object = UNSET,
    processed_at: datetime | None | object = UNSET,
) -> Document:
    document.processing_status = processing_status
    if error_message is not UNSET:
        document.error_message = error_message
    if processed_at is not UNSET:
        document.processed_at = processed_at
    db.commit()
    db.refresh(document)
    return document


def resolve_upload_root(upload_dir: str | Path, *, base_dir: Path) -> Path:
    upload_root = Path(upload_dir)
    if not upload_root.is_absolute():
        upload_root = base_dir / upload_root
    return upload_root


def store_document_file(
    *,
    upload_root: Path,
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    original_filename: str,
    content: bytes,
    team_id: int | None = None,
) -> tuple[str, str]:
    suffix = Path(original_filename).suffix.lower()
    internal_filename = f"{uuid.uuid4().hex}{suffix}"

    if scope == KnowledgeBaseScope.PERSONAL:
        relative_path = Path("personal") / f"knowledge_base_{knowledge_base_id}" / internal_filename
    else:
        if team_id is None:
            raise ValueError("team_id is required for team knowledge base uploads.")
        relative_path = (
            Path("team")
            / f"team_{team_id}"
            / f"knowledge_base_{knowledge_base_id}"
            / internal_filename
        )

    destination = upload_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)

    return internal_filename, relative_path.as_posix()
