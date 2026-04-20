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
    PARSED = "parsed"
    INDEXED = "indexed"
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
