from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import re
from typing import Protocol


CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_NONE = "none"

_SUPPORTED_EXTENSION_PATTERN = re.compile(r"\.(?:md|txt|pdf|docx)\b", re.IGNORECASE)
_WORD_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)
_CAMEL_CASE_BOUNDARY_PATTERN = re.compile(r"(?<=[a-z0-9])(?=[A-Z][a-z])")
_SEPARATOR_PATTERN = re.compile(r"[^a-z0-9\u4e00-\u9fff]+", re.IGNORECASE)

_KB_WIDE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:当前|整个|全部|所有)?知识库",
        r"当前语料",
        r"全部文档",
        r"所有文档",
        r"\bknowledge\s+base\b",
        r"\ball\s+(?:the\s+)?documents\b",
        r"\bentire\s+(?:collection|corpus)\b",
    )
)

_DOCUMENT_REQUEST_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"文档",
        r"文件",
        r"\bdocument\b",
        r"\bfile\b",
        r"\bguide\b",
    )
)

_GENERIC_TERMS = frozenset(
    {
        "all",
        "content",
        "cover",
        "current",
        "document",
        "documents",
        "file",
        "files",
        "give",
        "knowledge",
        "main",
        "me",
        "of",
        "overview",
        "please",
        "summary",
        "summarize",
        "the",
        "what",
        "总结",
        "概括",
        "归纳",
        "文档",
        "文件",
        "内容",
        "介绍",
        "主要",
        "当前",
        "知识库",
    }
)


class DocumentTarget(Protocol):
    id: int
    original_filename: str


@dataclass(frozen=True, slots=True)
class TargetDocumentDecision:
    target_document_ids: tuple[int, ...]
    matched_terms: tuple[str, ...]
    confidence: str
    reason: str
    target_requested: bool


@dataclass(frozen=True, slots=True)
class _DocumentNameCandidate:
    document_id: int
    display_term: str
    normalized_filename: str
    normalized_stem: str
    stem_tokens: tuple[str, ...]


def resolve_target_documents(
    query: str,
    documents: Sequence[DocumentTarget],
) -> TargetDocumentDecision:
    normalized_query = _normalize_text(query)
    if not normalized_query or _is_kb_wide_request(query):
        return _knowledge_base_decision()

    candidates = _build_document_candidates(documents)
    high_matches = [candidate for candidate in candidates if _is_high_confidence_match(normalized_query, candidate)]
    if high_matches:
        return _matched_decision(high_matches, confidence=CONFIDENCE_HIGH, reason="filename_stem_match")

    medium_matches = _medium_confidence_matches(normalized_query, candidates)
    if medium_matches:
        return _matched_decision(
            medium_matches,
            confidence=CONFIDENCE_MEDIUM,
            reason="filename_token_overlap",
        )

    if _looks_like_document_request(query):
        return TargetDocumentDecision(
            target_document_ids=(),
            matched_terms=_extract_requested_terms(query),
            confidence=CONFIDENCE_NONE,
            reason="requested_document_not_found",
            target_requested=True,
        )

    return _knowledge_base_decision()


def _build_document_candidates(documents: Sequence[DocumentTarget]) -> list[_DocumentNameCandidate]:
    candidates: list[_DocumentNameCandidate] = []
    for document in documents:
        original_filename = str(getattr(document, "original_filename", "") or "").strip()
        if not original_filename:
            continue
        basename = original_filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
        stem = _strip_supported_extension(basename)
        normalized_stem = _normalize_text(stem)
        if not normalized_stem:
            continue
        candidates.append(
            _DocumentNameCandidate(
                document_id=int(document.id),
                display_term=_display_term(stem),
                normalized_filename=_normalize_text(basename),
                normalized_stem=normalized_stem,
                stem_tokens=_meaningful_tokens(normalized_stem),
            )
        )
    return candidates


def _is_high_confidence_match(query: str, candidate: _DocumentNameCandidate) -> bool:
    if _contains_normalized_phrase(query, candidate.normalized_filename):
        return True
    return _contains_normalized_phrase(query, candidate.normalized_stem)


def _medium_confidence_matches(
    query: str,
    candidates: Sequence[_DocumentNameCandidate],
) -> list[_DocumentNameCandidate]:
    query_tokens = set(_meaningful_tokens(query))
    scored: list[tuple[float, _DocumentNameCandidate]] = []
    for candidate in candidates:
        candidate_tokens = set(candidate.stem_tokens)
        overlap = query_tokens & candidate_tokens
        if len(overlap) < 2:
            continue
        coverage = len(overlap) / max(1, len(candidate_tokens))
        if coverage < 0.6:
            continue
        scored.append((coverage, candidate))
    if not scored:
        return []

    best_score = max(score for score, _ in scored)
    return [candidate for score, candidate in scored if score == best_score]


def _matched_decision(
    candidates: Sequence[_DocumentNameCandidate],
    *,
    confidence: str,
    reason: str,
) -> TargetDocumentDecision:
    ordered = sorted(candidates, key=lambda candidate: candidate.document_id)
    return TargetDocumentDecision(
        target_document_ids=tuple(candidate.document_id for candidate in ordered),
        matched_terms=tuple(candidate.display_term for candidate in ordered),
        confidence=confidence,
        reason=reason,
        target_requested=True,
    )


def _knowledge_base_decision() -> TargetDocumentDecision:
    return TargetDocumentDecision(
        target_document_ids=(),
        matched_terms=(),
        confidence=CONFIDENCE_NONE,
        reason="knowledge_base_overview",
        target_requested=False,
    )


def _is_kb_wide_request(query: str) -> bool:
    return any(pattern.search(query) for pattern in _KB_WIDE_PATTERNS)


def _looks_like_document_request(query: str) -> bool:
    return bool(_SUPPORTED_EXTENSION_PATTERN.search(query)) or any(
        pattern.search(query) for pattern in _DOCUMENT_REQUEST_PATTERNS
    )


def _extract_requested_terms(query: str) -> tuple[str, ...]:
    normalized = _normalize_text(_SUPPORTED_EXTENSION_PATTERN.sub(" ", query))
    terms = _meaningful_tokens(normalized)
    return (" ".join(terms),) if terms else ()


def _meaningful_tokens(text: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in _WORD_PATTERN.findall(text.casefold())
        if token not in _GENERIC_TERMS and len(token) > 1
    )


def _contains_normalized_phrase(query: str, phrase: str) -> bool:
    if not phrase:
        return False
    return f" {phrase} " in f" {query} "


def _strip_supported_extension(filename: str) -> str:
    return _SUPPORTED_EXTENSION_PATTERN.sub("", filename).strip()


def _display_term(stem: str) -> str:
    return " ".join(_WORD_PATTERN.findall(_normalize_text(stem)))


def _normalize_text(value: str) -> str:
    camel_split = _CAMEL_CASE_BOUNDARY_PATTERN.sub(" ", value)
    return " ".join(_SEPARATOR_PATTERN.sub(" ", camel_split).casefold().split())


__all__ = [
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_NONE",
    "TargetDocumentDecision",
    "resolve_target_documents",
]
