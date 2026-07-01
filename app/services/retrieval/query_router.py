from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.retrieval.types import RetrievalMode


TECHNICAL_REASON = "question contains API/path/config/code-like tokens"
RELATION_REASON = "question asks about entity relations or dependencies"
OVERVIEW_REASON = "question asks for overview or summary"
DEFAULT_REASON = "default factual question"


@dataclass(frozen=True)
class QueryRouteDecision:
    selected_mode: RetrievalMode
    reason: str


_TECHNICAL_PATTERNS = [
    re.compile(r"(?<!\w)/(?:api|v\d+|app|tests|docs|frontend|scripts|alembic|worker-go)(?:/[\w.{}:-]+)+", re.I),
    re.compile(r"\b(?:app|tests|docs|frontend|scripts|alembic|worker-go)/(?:[\w.{}:-]+/)*[\w.{}:-]+", re.I),
    re.compile(r"\.env(?:\.[\w-]+)?\b"),
    re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b"),
    re.compile(r"\b[a-z]+_[a-z0-9_]+\b"),
    re.compile(r"\b[a-z0-9]+-[a-z0-9-]+\b"),
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\(\)"),
    re.compile(r"\b(?:npm\s+run|pnpm|pytest|curl)\b", re.I),
    re.compile(r"\bpython\s+[\w./-]+\.py\b", re.I),
    re.compile(r"\bHTTP\s*(?:401|403|404|500)\b", re.I),
    re.compile(r"\b(?:401|403|404|500)\b"),
]

_CODE_IDENTIFIER_PATTERNS = [
    re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b"),
    re.compile(r"\b(?!PureLink\b)[A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*\b"),
]

_TECHNICAL_KEYWORDS = {
    "migration",
    "schema",
    "endpoint",
    "middleware",
    "trace_id",
    "config",
    "error code",
    "api",
}

_RELATION_KEYWORDS = {
    "关系",
    "关联",
    "依赖",
    "影响",
    "属于",
    "连接",
    "权限",
    "谁可以",
    "谁负责",
    "谁调用",
    "调用链",
    "上下游",
    "source",
    "target",
    "relation",
    "dependency",
    "permission",
    "ownership",
    "linked to",
    "connected to",
}

_OVERVIEW_KEYWORDS = {
    "总结",
    "概览",
    "整体",
    "介绍",
    "有哪些",
    "主要内容",
    "整体架构",
    "overview",
    "summary",
    "summarize",
    "high level",
    "what are the main",
}


def route_query(query: str) -> QueryRouteDecision:
    normalized = " ".join(query.strip().split())
    lowered = normalized.lower()

    if _contains_technical_signal(normalized, lowered):
        return QueryRouteDecision(
            selected_mode=RetrievalMode.HYBRID_TEXT,
            reason=TECHNICAL_REASON,
        )
    if _contains_any(lowered, _RELATION_KEYWORDS):
        return QueryRouteDecision(
            selected_mode=RetrievalMode.GRAPH_VECTOR_MIX,
            reason=RELATION_REASON,
        )
    if _contains_any(lowered, _OVERVIEW_KEYWORDS):
        return QueryRouteDecision(
            selected_mode=RetrievalMode.OVERVIEW,
            reason=OVERVIEW_REASON,
        )
    if _contains_code_identifier_signal(normalized):
        return QueryRouteDecision(
            selected_mode=RetrievalMode.HYBRID_TEXT,
            reason=TECHNICAL_REASON,
        )
    return QueryRouteDecision(
        selected_mode=RetrievalMode.CHUNK_ONLY,
        reason=DEFAULT_REASON,
    )


def _contains_technical_signal(query: str, lowered: str) -> bool:
    if any(pattern.search(query) for pattern in _TECHNICAL_PATTERNS):
        return True
    return any(_contains_keyword(lowered, keyword) for keyword in _TECHNICAL_KEYWORDS)


def _contains_code_identifier_signal(query: str) -> bool:
    return any(pattern.search(query) for pattern in _CODE_IDENTIFIER_PATTERNS)


def _contains_any(lowered: str, keywords: set[str]) -> bool:
    return any(keyword in lowered for keyword in keywords)


def _contains_keyword(lowered: str, keyword: str) -> bool:
    return re.search(rf"(?<![a-z0-9_]){re.escape(keyword)}(?![a-z0-9_])", lowered) is not None


__all__ = [
    "DEFAULT_REASON",
    "OVERVIEW_REASON",
    "QueryRouteDecision",
    "RELATION_REASON",
    "TECHNICAL_REASON",
    "route_query",
]
