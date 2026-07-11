from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.retrieval.types import RetrievalMode


TECHNICAL_REASON = "question contains exact technical identifier"
RELATION_REASON = "question asks about explicit entity relations"
OVERVIEW_REASON = "question asks for overview or summary"
DEFAULT_REASON = "default factual question"
LOW_CONFIDENCE_REASON = "low-confidence router signal; defaulting to chunk_only"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_MANUAL = "manual"


@dataclass(frozen=True)
class QueryRouteDecision:
    selected_mode: RetrievalMode
    reason: str
    confidence: str = CONFIDENCE_HIGH


_OVERVIEW_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in (
        r"总结",
        r"概括",
        r"归纳",
        r"综述",
        r"主要内容",
        r"核心内容",
        r"主要包含哪些内容",
        r"主要包含什么",
        r"哪些方面",
        r"主要环节",
        r"有哪些主要",
        r"有哪些部分",
        r"包括哪些内容",
        r"列出所有",
        r"列出.*主要",
        r"整体介绍",
        r"整体架构",
        r"文档讲了什么",
        r"\boverview\b",
        r"\bsummarize\b",
        r"\bsummary\b",
        r"\bmain topics\b",
        r"\blist all\b",
        r"\bwhat are the main\b",
    )
]

_RELATION_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in (
        r"什么关系",
        r"关系",
        r"关联",
        r"依赖",
        r"属于(?:哪个|什么)?(?:组|组织|团队|模块|系统)?",
        r"包含",
        r"调用",
        r"负责",
        r"合作",
        r"协作",
        r"伙伴",
        r"同事",
        r"隶属",
        r"连接",
        r"组成",
        r"与.+之间",
        r"\brelationship\b",
        r"\bdepends on\b",
        r"\bbelong(?:s)? to\b",
        r"\bpart of\b",
        r"\bworks with\b",
    )
]

_WEAK_RELATION_TERMS = {"影响", "权限", "成员", "作用", "特点", "介绍"}

_EXACT_TECHNICAL_PATTERNS = [
    re.compile(r"(?<!\w)/(?:api|v\d+|app|tests|docs|frontend|scripts|alembic|worker-go)(?:/[\w.{}:-]+)+", re.I),
    re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[\w./{}:-]+", re.I),
    re.compile(r"\b(?:app|tests|docs|frontend|scripts|alembic|worker-go)/(?:[\w.{}:-]+/)*[\w.{}:-]+", re.I),
    re.compile(r"\.env(?:\.[\w-]+)?\b"),
    re.compile(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b"),
    re.compile(r"\b[a-z][a-z0-9]+_[a-z0-9_]+\b"),
    re.compile(r"\b__[A-Za-z0-9_]+__\b"),
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\s*\("),
    re.compile(r"\b(?:docker\s+compose|npm\s+run|pnpm|pytest|curl)\b", re.I),
    re.compile(r"\bpython\s+[\w./-]+\.py\b", re.I),
    re.compile(r"\bHTTP\s*(?:401|403|404|500)\b", re.I),
    re.compile(r"\b(?:401|403|404|500)\b"),
    re.compile(r"`[^`]+`"),
    re.compile(r"['\"][^'\"]+['\"]"),
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\b"),
]

_FUNCTION_NAME_TERMS = {"depends"}
_CLI_PHRASES = {"docker compose down -v"}
_TECHNICAL_PHRASES = {"source locator"}
_ATTRIBUTE_PHRASES = ("有什么特点",)

_CONNECTOR_PATTERN = re.compile(r"\s(?:和|与|及|、|and)\s?", re.I)
_ENTITY_TOKEN_PATTERN = re.compile(
    r"\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*)*\b|"
    r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)*\b|"
    r"\b[a-z]+_[a-z0-9_]+\b|"
    r"[\u4e00-\u9fffA-Za-z0-9_]+(?:Block|Chunk|Parser|API|MVCC|Labs|Systems)"
)


def route_query(query: str) -> QueryRouteDecision:
    normalized = " ".join(query.strip().split())
    lowered = normalized.lower()

    if _contains_overview_signal(normalized):
        return QueryRouteDecision(
            selected_mode=RetrievalMode.OVERVIEW,
            reason=OVERVIEW_REASON,
            confidence=CONFIDENCE_HIGH,
        )

    if _contains_relation_signal(normalized, lowered):
        return QueryRouteDecision(
            selected_mode=RetrievalMode.GRAPH_VECTOR_MIX,
            reason=RELATION_REASON,
            confidence=CONFIDENCE_HIGH,
        )

    if _contains_attribute_question(normalized):
        return QueryRouteDecision(
            selected_mode=RetrievalMode.CHUNK_ONLY,
            reason=DEFAULT_REASON,
            confidence=CONFIDENCE_LOW,
        )

    if _contains_exact_technical_signal(normalized, lowered):
        return QueryRouteDecision(
            selected_mode=RetrievalMode.HYBRID_TEXT,
            reason=TECHNICAL_REASON,
            confidence=CONFIDENCE_HIGH,
        )

    if _contains_weak_signal(normalized, lowered):
        return QueryRouteDecision(
            selected_mode=RetrievalMode.CHUNK_ONLY,
            reason=LOW_CONFIDENCE_REASON,
            confidence=CONFIDENCE_LOW,
        )

    return QueryRouteDecision(
        selected_mode=RetrievalMode.CHUNK_ONLY,
        reason=DEFAULT_REASON,
        confidence=CONFIDENCE_LOW,
    )


def _contains_overview_signal(query: str) -> bool:
    if any(pattern.search(query) for pattern in _OVERVIEW_PATTERNS):
        return True
    return bool(re.search(r"成员有哪些[？?]?$", query))


def _contains_relation_signal(query: str, lowered: str) -> bool:
    if not any(pattern.search(query) for pattern in _RELATION_PATTERNS):
        return False
    if any(term in query for term in _WEAK_RELATION_TERMS) and not _has_strong_relation_phrase(query):
        return False
    return _has_two_entities(query) or _has_single_entity_relation_phrase(query, lowered)


def _has_strong_relation_phrase(query: str) -> bool:
    return any(
        phrase in query
        for phrase in (
            "什么关系",
            "属于哪个",
            "属于什么",
            "合作",
            "协作",
            "伙伴",
            "同事",
            "隶属",
            "依赖",
            "调用",
            "与",
            "和",
        )
    )


def _has_single_entity_relation_phrase(query: str, lowered: str) -> bool:
    return (
        "属于哪个" in query
        or "属于什么" in query
        or "隶属" in query
        or "belongs to" in lowered
        or "part of" in lowered
    )


def _has_two_entities(query: str) -> bool:
    if _CONNECTOR_PATTERN.search(query):
        return True
    return len({match.group(0).strip() for match in _ENTITY_TOKEN_PATTERN.finditer(query) if match.group(0).strip()}) >= 2


def _contains_exact_technical_signal(query: str, lowered: str) -> bool:
    if any(pattern.search(query) for pattern in _EXACT_TECHNICAL_PATTERNS):
        return True
    if any(phrase in lowered for phrase in _CLI_PHRASES):
        return True
    if any(phrase in lowered for phrase in _TECHNICAL_PHRASES):
        return True
    return any(_contains_word(lowered, term) for term in _FUNCTION_NAME_TERMS)


def _contains_attribute_question(query: str) -> bool:
    return any(phrase in query for phrase in _ATTRIBUTE_PHRASES)


def _contains_weak_signal(query: str, lowered: str) -> bool:
    return (
        any(term in query for term in _WEAK_RELATION_TERMS)
        or any(term in lowered for term in ("api", "config", "dependency", "mvcc"))
    )


def _contains_word(lowered: str, keyword: str) -> bool:
    return re.search(rf"(?<![a-z0-9_]){re.escape(keyword)}(?![a-z0-9_])", lowered) is not None


__all__ = [
    "CONFIDENCE_HIGH",
    "CONFIDENCE_LOW",
    "CONFIDENCE_MANUAL",
    "CONFIDENCE_MEDIUM",
    "DEFAULT_REASON",
    "LOW_CONFIDENCE_REASON",
    "OVERVIEW_REASON",
    "QueryRouteDecision",
    "RELATION_REASON",
    "TECHNICAL_REASON",
    "route_query",
]
