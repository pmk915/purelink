from __future__ import annotations

from enum import StrEnum


def enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_class]


class KnowledgeBaseScope(StrEnum):
    PERSONAL = "personal"
    TEAM = "team"


class DocumentReviewStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class DocumentProcessingStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PARSED = "parsed"
    INDEXED = "indexed"
    READY = "ready"
    FAILED = "failed"


DocumentStatus = DocumentProcessingStatus


class DocumentTaskType(StrEnum):
    PARSE = "parse"
    CHUNK = "chunk"
    EMBED = "embed"
    INDEX = "index"


class DocumentTaskStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DocumentIndexType(StrEnum):
    VECTOR = "vector"
    GRAPH = "graph"
    LEXICAL = "lexical"


class DocumentIndexStatus(StrEnum):
    PENDING = "pending"
    INDEXING = "indexing"
    INDEXED = "indexed"
    STALE = "stale"
    FAILED = "failed"


class RetrievalFilteredReason(StrEnum):
    NOT_FILTERED = "not_filtered"
    NOT_SELECTED_AFTER_RERANK = "not_selected_after_rerank"
    LOW_SCORE = "low_score"
    INCOMPATIBLE_INDEX = "incompatible_index"
    STALE_INDEX = "stale_index"
    LEGACY_UNKNOWN_ALLOWED = "legacy_unknown_allowed"
    MISSING_INDEX = "missing_index"
    DOCUMENT_NOT_READY = "document_not_ready"
    PERMISSION_FILTERED = "permission_filtered"
    UNKNOWN = "unknown"


class DocumentBlockType(StrEnum):
    TEXT = "text"
    HEADING = "heading"
    TABLE = "table"
    CODE = "code"
    IMAGE = "image"
    FORMULA = "formula"
    UNKNOWN = "unknown"


class ProcessingJobType(StrEnum):
    DOCUMENT_PROCESS = "document_process"
    DOCUMENT_INDEX = "document_index"


class ProcessingJobTrigger(StrEnum):
    PROCESS = "process"
    RETRY = "retry"
    REPROCESS = "reprocess"
    INDEX = "index"


class ProcessingJobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class TeamMemberRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class TeamMemberStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    REMOVED = "removed"


class TeamInviteStatus(StrEnum):
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"
