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

EVIDENCE_QUERY_GENERIC = "generic_factual"
EVIDENCE_QUERY_ATTRIBUTE = "entity_attribute"
EVIDENCE_QUERY_DEFINITION = "entity_definition"
EVIDENCE_QUERY_REASON = "entity_reason"
EVIDENCE_QUERY_RELATION = "entity_relation"
EVIDENCE_QUERY_TECHNICAL = "exact_technical"
EVIDENCE_QUERY_OVERVIEW = "overview"

EVIDENCE_ATTRIBUTE_ALIASES: dict[str, tuple[str, ...]] = {
    "location": (
        "在哪里",
        "在哪",
        "办公地点",
        "办公城市",
        "城市",
        "地址",
        "location",
        "office",
        "city",
        "address",
    ),
    "processor": ("处理器", "cpu", "gpu", "芯片", "processor", "chipset"),
    "color": ("颜色", "配色", "color", "colour", "finish"),
    "role": ("角色", "职位", "职务", "role", "position", "title"),
    "responsibility": ("负责", "职责", "责任", "responsibility", "responsibilities", "owns"),
    "group": ("隶属", "属于哪个组", "属于哪个团队", "group", "team", "belongs to"),
    "configuration": ("配置", "环境变量", "config", "configuration", "environment variable"),
    "default_value": ("默认值", "缺省值", "default value", "defaults to", "default"),
    "supported_values": (
        "支持哪些值",
        "可选值",
        "允许值",
        "supported values",
        "valid values",
        "options",
    ),
    "file_types": (
        "文件类型",
        "文件格式",
        "文本格式",
        "扩展名",
        "file types",
        "file formats",
        "formats",
        "extensions",
    ),
    "version": ("版本", "version", "release"),
    "date": ("日期", "时间", "哪一年", "什么时候", "date", "year", "when"),
}

_TECHNICAL_IDENTIFIER_PATTERNS = (
    re.compile(r"`([^`]+)`"),
    re.compile(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b"),
    re.compile(r"\b[a-z][a-z0-9]+_[a-z0-9_]+\b"),
    re.compile(r"\b__[A-Za-z0-9_]+__\b"),
    re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[\w./{}:-]+", re.IGNORECASE),
    re.compile(r"(?<!\w)/(?:api|v\d+)(?:/[\w.{}:-]+)+", re.IGNORECASE),
    re.compile(r"\b(?:app|tests|docs|frontend|scripts|alembic|worker-go)/(?:[\w.{}:-]+/)*[\w.{}:-]+", re.IGNORECASE),
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\(\)"),
    re.compile(r"(?:中|调用|使用)\s*([A-Z][A-Za-z0-9_]+)(?=\s*(?:的|在|是))"),
    re.compile(r"\b[\w.-]+\.(?:py|md|txt|pdf|docx|ya?ml|json)\b", re.IGNORECASE),
    re.compile(r"\b(?:docker\s+compose(?:\s+[A-Za-z0-9_.-]+)+|npm\s+run\s+[A-Za-z0-9_:-]+|pnpm\s+[A-Za-z0-9_:-]+|pytest(?:\s+[A-Za-z0-9_./:-]+)*|curl\s+\S+)", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class EvidenceQueryAnalysis:
    query_type: str
    entities: tuple[str, ...]
    requested_attributes: tuple[str, ...]
    technical_identifiers: tuple[str, ...]
    overview_requested: bool
    list_all_requested: bool


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


def analyze_evidence_query(query: str) -> EvidenceQueryAnalysis:
    normalized = " ".join(str(query or "").split())
    lowered = normalized.casefold()
    requested_attributes = tuple(
        name
        for name, aliases in EVIDENCE_ATTRIBUTE_ALIASES.items()
        if any(alias.casefold() in lowered for alias in aliases)
    )
    technical_identifiers = extract_technical_identifiers(normalized)
    overview_requested = bool(
        re.search(
            r"总结|概括|归纳|综述|主要内容|\boverview\b|\bsummary\b|\bsummarize\b",
            normalized,
            re.IGNORECASE,
        )
    )
    list_all_requested = bool(
        re.search(
            r"列出所有|全部|所有|有哪些|哪些成员|\blist\s+all\b|\ball\s+(?:the\s+)?(?:items|members|documents)\b",
            normalized,
            re.IGNORECASE,
        )
    )
    query_type = _evidence_query_type(
        normalized,
        requested_attributes=requested_attributes,
        technical_identifiers=technical_identifiers,
        overview_requested=overview_requested,
        list_all_requested=list_all_requested,
    )
    return EvidenceQueryAnalysis(
        query_type=query_type,
        entities=_extract_evidence_entities(
            normalized,
            query_type=query_type,
            requested_attributes=requested_attributes,
            technical_identifiers=technical_identifiers,
        ),
        requested_attributes=requested_attributes,
        technical_identifiers=technical_identifiers,
        overview_requested=overview_requested,
        list_all_requested=list_all_requested,
    )


def extract_technical_identifiers(query: str) -> tuple[str, ...]:
    identifiers: list[str] = []
    for pattern in _TECHNICAL_IDENTIFIER_PATTERNS:
        for match in pattern.finditer(query):
            value = match.group(1) if match.groups() else match.group(0)
            cleaned = value.strip("`'\" ")
            if cleaned:
                identifiers.append(cleaned)
    return tuple(dict.fromkeys(identifiers))


def evidence_attribute_aliases(attribute: str) -> tuple[str, ...]:
    return EVIDENCE_ATTRIBUTE_ALIASES.get(attribute, (attribute,))


def _evidence_query_type(
    query: str,
    *,
    requested_attributes: tuple[str, ...],
    technical_identifiers: tuple[str, ...],
    overview_requested: bool,
    list_all_requested: bool,
) -> str:
    lowered = query.casefold()
    if overview_requested or list_all_requested:
        return EVIDENCE_QUERY_OVERVIEW
    if re.search(r"什么关系|有.*关系|\brelationship\b|\brelated\b", query, re.IGNORECASE):
        return EVIDENCE_QUERY_RELATION
    if technical_identifiers:
        return EVIDENCE_QUERY_TECHNICAL
    if requested_attributes:
        return EVIDENCE_QUERY_ATTRIBUTE
    if "为什么" in query or re.search(r"\bwhy\b", lowered):
        return EVIDENCE_QUERY_REASON
    if any(term in lowered for term in ("是谁", "是什么", "介绍", "定义", "what is")):
        return EVIDENCE_QUERY_DEFINITION
    return EVIDENCE_QUERY_GENERIC


def _extract_evidence_entities(
    query: str,
    *,
    query_type: str,
    requested_attributes: tuple[str, ...],
    technical_identifiers: tuple[str, ...],
) -> tuple[str, ...]:
    if query_type == EVIDENCE_QUERY_RELATION:
        match = re.search(
            r"(.+?)(?:和|与|跟|\band\b)(.+?)(?:是什么关系|有.*关系|\brelationship\b|\brelated\b|[？?]?$)",
            query,
            re.IGNORECASE,
        )
        if match:
            return tuple(
                item
                for item in (_clean_entity_text(match.group(1)), _clean_entity_text(match.group(2)))
                if item
            )

    if query_type == EVIDENCE_QUERY_REASON:
        prefix_match = re.match(r"\s*(.+?)\s*为什么", query)
        if prefix_match:
            entity = _clean_entity_text(prefix_match.group(1))
            if entity:
                return (entity,)
        suffix_match = re.search(
            r"为什么\s*(.+?)(?:需要|会|要|使用|采用|适合|拒绝|触发|导致)",
            query,
        )
        if suffix_match:
            entity = _clean_entity_text(suffix_match.group(1))
            if entity:
                return (entity,)

    cleaned = query
    for identifier in technical_identifiers:
        cleaned = re.sub(re.escape(identifier), " ", cleaned, flags=re.IGNORECASE)
    for attribute in requested_attributes:
        for alias in evidence_attribute_aliases(attribute):
            cleaned = re.sub(re.escape(alias), " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"为什么|是谁|是什么|是多少|在哪里|在哪|位于哪里|有什么|什么|如何|怎么|请问|请|的|型号|作用|用途|特点|特征|支持|使用|调用|保存|办公|文本|哪些值|哪些|值|列出所有|全部|所有|总结|概括|归纳|"
        r"\b(?:why|what|where|when|how|does|do|is|are|the|a|an|please|list|all)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    entity = _clean_entity_text(cleaned)
    return (entity,) if entity else ()


def _clean_entity_text(value: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value)
    return " ".join(normalized.split()).strip()


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
    "EVIDENCE_ATTRIBUTE_ALIASES",
    "EVIDENCE_QUERY_ATTRIBUTE",
    "EVIDENCE_QUERY_DEFINITION",
    "EVIDENCE_QUERY_GENERIC",
    "EVIDENCE_QUERY_OVERVIEW",
    "EVIDENCE_QUERY_REASON",
    "EVIDENCE_QUERY_RELATION",
    "EVIDENCE_QUERY_TECHNICAL",
    "EvidenceQueryAnalysis",
    "TargetDocumentDecision",
    "analyze_evidence_query",
    "evidence_attribute_aliases",
    "extract_technical_identifiers",
    "resolve_target_documents",
]
