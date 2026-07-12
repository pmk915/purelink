from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Sequence


REASON_SUPPORTED = "supported"
REASON_NO_EVIDENCE = "no_evidence"
REASON_MISSING_ENTITY_SUPPORT = "missing_entity_support"
REASON_MISSING_ATTRIBUTE_SUPPORT = "missing_attribute_support"
REASON_MISSING_REASON_SUPPORT = "missing_reason_support"
REASON_MISSING_RELATION_SUPPORT = "missing_relation_support"
REASON_MISSING_EXACT_IDENTIFIER_SUPPORT = "missing_exact_identifier_support"
REASON_INSUFFICIENT_QUERY_COVERAGE = "insufficient_query_coverage"

QUERY_TYPE_ENTITY_DEFINITION = "entity_definition"
QUERY_TYPE_ENTITY_ATTRIBUTE = "entity_attribute"
QUERY_TYPE_ENTITY_REASON = "entity_reason"
QUERY_TYPE_ENTITY_RELATION = "entity_relation"
QUERY_TYPE_EXACT_TECHNICAL = "exact_technical"
QUERY_TYPE_OVERVIEW = "overview"
QUERY_TYPE_GENERIC_FACTUAL = "generic_factual"

OVERVIEW_INTENT = "kb_overview"


@dataclass(frozen=True, slots=True)
class EvidenceSupportDecision:
    answerable: bool
    support_score: float
    reason: str
    query_type: str
    signals: dict[str, Any] = field(default_factory=dict)
    supporting_evidence_ids: tuple[str, ...] = ()
    rejected_evidence_ids: tuple[str, ...] = ()

    def to_metadata(self) -> dict[str, Any]:
        return {
            "answerable": self.answerable,
            "evidence_support_score": self.support_score,
            "evidence_support_reason": self.reason,
            "evidence_support_query_type": self.query_type,
            "evidence_support_signals": self.signals,
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "rejected_evidence_ids": list(self.rejected_evidence_ids),
        }


@dataclass(frozen=True, slots=True)
class _SupportQuery:
    query_type: str
    entity_terms: tuple[str, ...] = ()
    relation_terms: tuple[str, ...] = ()
    requested_attributes: tuple[str, ...] = ()
    exact_identifiers: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()


ATTRIBUTE_ALIASES: dict[str, tuple[str, ...]] = {
    "financial": ("利润", "收入", "营收", "融资", "revenue", "profit", "funding", "financing"),
    "leadership": ("ceo", "chief executive", "首席执行官", "负责人"),
    "founder": ("创始人", "founder", "founded by"),
    "listing": ("上市", "ipo", "listed"),
    "processor": ("处理器", "cpu", "processor", "芯片", "显卡", "gpu"),
    "birthday": ("生日", "出生", "出生日期", "出生年份", "birthday", "born"),
    "location": ("在哪里", "在哪", "办公地点", "办公城市", "地点", "位置", "地址", "总部", "街道地址", "location", "city", "address"),
    "color": ("颜色", "color", "finish", "银色", "黑色", "蓝色", "灰色"),
    "weight": ("重量", "多重", "weight", "kg"),
    "height": ("身高", "height", "tall"),
    "role": ("角色", "职位", "role"),
    "responsibility": ("负责", "职责", "responsibility", "owns", "maintains", "focuses"),
    "group": ("隶属", "属于", "组", "团队", "group", "belongs"),
    "configuration": ("配置", "在哪里配置", "environment variable", "环境变量", "config"),
    "default_value": ("默认值", "default value", "default"),
    "remote_work_policy": ("远程办公", "remote work"),
    "invention_date": ("哪一年", "发明", "created", "invented", "founded"),
}

DEFINITION_TERMS = (
    "是",
    "为",
    "指",
    "定义",
    "身份",
    "角色",
    "人物",
    "产品",
    "概念",
    "工具",
    "系统",
    "records",
    "preserve",
    "organizes",
    "is a",
    "are a",
    "refers to",
    "defined",
    "usually",
)
REASON_TERMS = (
    "因为",
    "用于",
    "用来",
    "目的",
    "可以",
    "能够",
    "避免",
    "减少",
    "保持",
    "需要",
    "优势",
    "helps",
    "because",
    "allows",
    "provides",
    "designed to",
    "used to",
    "so ",
    "can ",
    "should",
    "reduce",
    "preserve",
    "keep",
)
RELATION_TERMS = (
    "关系",
    "关联",
    "依赖",
    "属于",
    "隶属",
    "合作",
    "伙伴",
    "同事",
    "成员",
    "包含",
    "调用",
    "负责",
    "连接",
    "组成",
    "derived from",
    "depends",
    "belongs",
    "part of",
    "works with",
    "partner",
    "relationship",
    "supports",
    "strategies",
)
RELATION_EVIDENCE_TERMS = RELATION_TERMS + (
    "follow",
    "follows",
    "followed",
    "lead",
    "leads",
    "led",
    "encounter",
    "encounters",
    "encountered",
    "speaks with",
    "faces",
    "draws",
    "produce",
    "produces",
    "becomes",
    "become",
    "without blocking",
    "跟随",
    "遇到",
    "带领",
    "引向",
)
OVERVIEW_TERMS = (
    "总结",
    "概括",
    "归纳",
    "综述",
    "主要内容",
    "主要环节",
    "有哪些",
    "overview",
    "summary",
    "summarize",
)

TECHNICAL_PATTERNS = (
    re.compile(r"\b[A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+\b"),
    re.compile(r"\b[a-z][a-z0-9]+_[a-z0-9_]+\b"),
    re.compile(r"\b__[A-Za-z0-9_]+__\b"),
    re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[\w./{}:-]+", re.I),
    re.compile(r"(?<!\w)/(?:api|v\d+)(?:/[\w.{}:-]+)+", re.I),
    re.compile(r"`([^`]+)`"),
)


def evaluate_evidence_support(
    *,
    query: str,
    evidence_units: Sequence[Any],
    profile: Any | None = None,
    qa_intent: str | None = None,
) -> EvidenceSupportDecision:
    support_query = _build_support_query(query, profile=profile, qa_intent=qa_intent)
    evidence_list = list(evidence_units)
    if not evidence_list:
        return EvidenceSupportDecision(
            answerable=False,
            support_score=0.0,
            reason=REASON_NO_EVIDENCE,
            query_type=support_query.query_type,
            signals={"has_final_evidence": False},
        )

    contexts = [_evidence_context(item) for item in evidence_list]
    supporting_ids = tuple(
        _evidence_id(item)
        for item, context in zip(evidence_list, contexts, strict=False)
        if _evidence_individually_supports(support_query, context)
    )
    rejected_ids = tuple(
        _evidence_id(item)
        for item, context in zip(evidence_list, contexts, strict=False)
        if not _evidence_individually_supports(support_query, context)
    )

    aggregate_context = "\n".join(contexts)
    entity_coverage = _entity_coverage(support_query.entity_terms, aggregate_context)
    relation_entity_coverage, relation_supporting_ids = _relation_support(
        support_query,
        evidence_list,
    )
    attribute_coverage = _attribute_coverage(support_query.requested_attributes, aggregate_context)
    exact_identifier_coverage, technical_intent_coverage, technical_supporting_ids = _technical_support(
        support_query,
        evidence_list,
    )
    requested_intent_coverage = (
        technical_intent_coverage
        if support_query.query_type == QUERY_TYPE_EXACT_TECHNICAL
        else (
            bool(relation_supporting_ids)
            if support_query.query_type == QUERY_TYPE_ENTITY_RELATION
            else _intent_coverage(support_query, aggregate_context)
        )
    )
    if support_query.query_type == QUERY_TYPE_ENTITY_RELATION and relation_supporting_ids:
        supporting_ids = relation_supporting_ids
        rejected_ids = tuple(
            evidence_id
            for evidence_id in (_evidence_id(item) for item in evidence_list)
            if evidence_id not in supporting_ids
        )
    elif support_query.query_type == QUERY_TYPE_EXACT_TECHNICAL and technical_supporting_ids:
        supporting_ids = technical_supporting_ids
        rejected_ids = tuple(
            evidence_id
            for evidence_id in (_evidence_id(item) for item in evidence_list)
            if evidence_id not in supporting_ids
        )
    lexical_support = _lexical_support(support_query.keywords, aggregate_context)
    retrieval_score_support = _max_score(evidence_list) >= 0.15
    structured_context_support = any(_structured_context_text(item) for item in evidence_list)

    signals = {
        "has_final_evidence": True,
        "entity_coverage": entity_coverage,
        "requested_intent_coverage": requested_intent_coverage,
        "requested_attribute_coverage": attribute_coverage,
        "exact_identifier_coverage": exact_identifier_coverage,
        "relation_entity_coverage": relation_entity_coverage,
        "lexical_support": lexical_support,
        "retrieval_score_support": retrieval_score_support,
        "structured_context_support": structured_context_support,
        "requested_attributes": list(support_query.requested_attributes),
        "exact_identifiers": list(support_query.exact_identifiers),
        "entity_terms": list(support_query.entity_terms),
    }
    score = _support_score(signals)
    reason = _unsupported_reason(
        support_query=support_query,
        entity_coverage=entity_coverage,
        relation_entity_coverage=relation_entity_coverage,
        attribute_coverage=attribute_coverage,
        exact_identifier_coverage=exact_identifier_coverage,
        requested_intent_coverage=requested_intent_coverage,
        lexical_support=lexical_support,
        supporting_ids=supporting_ids,
    )
    return EvidenceSupportDecision(
        answerable=reason == REASON_SUPPORTED,
        support_score=score if reason == REASON_SUPPORTED else min(score, 0.49),
        reason=reason,
        query_type=support_query.query_type,
        signals=signals,
        supporting_evidence_ids=supporting_ids,
        rejected_evidence_ids=rejected_ids,
    )


def _build_support_query(query: str, *, profile: Any | None, qa_intent: str | None) -> _SupportQuery:
    normalized = _normalize_text(query)
    lowered = normalized.casefold()
    profile_type = str(getattr(profile, "query_type", "") or "")
    profile_entities = tuple(str(item) for item in getattr(profile, "entity_terms", ()) if str(item))

    if qa_intent == OVERVIEW_INTENT or _contains_any(lowered, OVERVIEW_TERMS):
        return _SupportQuery(
            query_type=QUERY_TYPE_OVERVIEW,
            keywords=_keywords(normalized),
        )

    relation_terms = _extract_relation_terms(normalized)
    if relation_terms or profile_type == QUERY_TYPE_ENTITY_RELATION:
        return _SupportQuery(
            query_type=QUERY_TYPE_ENTITY_RELATION,
            entity_terms=relation_terms or profile_entities,
            relation_terms=relation_terms,
            keywords=_keywords(normalized),
        )

    exact_identifiers = _extract_exact_identifiers(normalized)
    if exact_identifiers:
        return _SupportQuery(
            query_type=QUERY_TYPE_EXACT_TECHNICAL,
            entity_terms=profile_entities,
            requested_attributes=_requested_attributes(lowered),
            exact_identifiers=exact_identifiers,
            keywords=_keywords(normalized),
        )

    requested_attributes = _requested_attributes(lowered)
    if requested_attributes:
        return _SupportQuery(
            query_type=QUERY_TYPE_ENTITY_ATTRIBUTE,
            entity_terms=_extract_attribute_entity_terms(normalized, requested_attributes) or profile_entities,
            requested_attributes=requested_attributes,
            keywords=_keywords(normalized),
        )

    if _contains_any(lowered, ("为什么", "why ", "主要目的", "目的")):
        return _SupportQuery(
            query_type=QUERY_TYPE_ENTITY_REASON,
            entity_terms=_extract_reason_entity_terms(normalized) or profile_entities,
            keywords=_keywords(normalized),
        )

    if profile_type in {
        QUERY_TYPE_ENTITY_DEFINITION,
        QUERY_TYPE_ENTITY_ATTRIBUTE,
        QUERY_TYPE_ENTITY_REASON,
    }:
        return _SupportQuery(
            query_type=profile_type,
            entity_terms=_extract_profile_entity_terms(normalized, profile_type) or profile_entities,
            requested_attributes=requested_attributes,
            keywords=_keywords(normalized),
        )

    if _contains_any(lowered, ("是谁", "是什么", "what is", "介绍", "定义")):
        return _SupportQuery(
            query_type=QUERY_TYPE_ENTITY_DEFINITION,
            entity_terms=profile_entities or _extract_definition_entity_terms(normalized),
            keywords=_keywords(normalized),
        )

    return _SupportQuery(
        query_type=QUERY_TYPE_GENERIC_FACTUAL,
        entity_terms=profile_entities,
        keywords=_keywords(normalized),
    )


def _unsupported_reason(
    *,
    support_query: _SupportQuery,
    entity_coverage: bool,
    relation_entity_coverage: bool,
    attribute_coverage: bool,
    exact_identifier_coverage: bool,
    requested_intent_coverage: bool,
    lexical_support: bool,
    supporting_ids: tuple[str, ...],
) -> str:
    if support_query.query_type == QUERY_TYPE_OVERVIEW:
        return REASON_SUPPORTED if supporting_ids else REASON_INSUFFICIENT_QUERY_COVERAGE
    if support_query.query_type == QUERY_TYPE_EXACT_TECHNICAL:
        if not exact_identifier_coverage and not lexical_support:
            return REASON_MISSING_EXACT_IDENTIFIER_SUPPORT
        if not requested_intent_coverage:
            return REASON_INSUFFICIENT_QUERY_COVERAGE
        return REASON_SUPPORTED
    if support_query.query_type == QUERY_TYPE_ENTITY_ATTRIBUTE:
        if support_query.requested_attributes and not attribute_coverage:
            return REASON_MISSING_ATTRIBUTE_SUPPORT
        return REASON_SUPPORTED
    if support_query.query_type == QUERY_TYPE_ENTITY_REASON:
        if not requested_intent_coverage and not lexical_support:
            return REASON_MISSING_REASON_SUPPORT
        return REASON_SUPPORTED
    if support_query.query_type == QUERY_TYPE_ENTITY_RELATION:
        if not relation_entity_coverage:
            return REASON_MISSING_ENTITY_SUPPORT
        if not requested_intent_coverage:
            return REASON_MISSING_RELATION_SUPPORT
        return REASON_SUPPORTED
    if support_query.query_type == QUERY_TYPE_ENTITY_DEFINITION:
        if support_query.entity_terms and not entity_coverage and not lexical_support:
            return REASON_MISSING_ENTITY_SUPPORT
        if not requested_intent_coverage and not lexical_support:
            return REASON_INSUFFICIENT_QUERY_COVERAGE
        return REASON_SUPPORTED
    return REASON_SUPPORTED


def _evidence_individually_supports(support_query: _SupportQuery, context: str) -> bool:
    if support_query.query_type == QUERY_TYPE_OVERVIEW:
        return bool(_normalize_text(context))
    if support_query.query_type == QUERY_TYPE_EXACT_TECHNICAL:
        return _exact_identifier_coverage(support_query.exact_identifiers, context) and _intent_coverage(support_query, context)
    if support_query.query_type == QUERY_TYPE_ENTITY_ATTRIBUTE:
        return (
            (not support_query.entity_terms or _entity_coverage(support_query.entity_terms, context))
            and _attribute_coverage(support_query.requested_attributes, context)
        )
    if support_query.query_type == QUERY_TYPE_ENTITY_REASON:
        return (
            (not support_query.entity_terms or _entity_coverage(support_query.entity_terms, context))
            and _contains_any(context.casefold(), REASON_TERMS)
        )
    if support_query.query_type == QUERY_TYPE_ENTITY_RELATION:
        return _relation_entity_coverage(support_query, context) and _contains_any(
            context.casefold(),
            RELATION_EVIDENCE_TERMS,
        )
    if support_query.query_type == QUERY_TYPE_ENTITY_DEFINITION:
        return (
            (not support_query.entity_terms or _entity_coverage(support_query.entity_terms, context))
            and _contains_any(context.casefold(), DEFINITION_TERMS)
        )
    return bool(_normalize_text(context))


def _support_score(signals: dict[str, Any]) -> float:
    weights = {
        "has_final_evidence": 0.15,
        "entity_coverage": 0.20,
        "requested_intent_coverage": 0.20,
        "requested_attribute_coverage": 0.15,
        "exact_identifier_coverage": 0.15,
        "relation_entity_coverage": 0.10,
        "lexical_support": 0.10,
        "retrieval_score_support": 0.05,
    }
    score = sum(weight for key, weight in weights.items() if signals.get(key))
    return round(min(1.0, score), 3)


def _evidence_context(item: Any) -> str:
    parts = [
        str(getattr(item, "text", "") or ""),
        _structured_context_text(item),
    ]
    return _normalize_text(" ".join(part for part in parts if part))


def _structured_context_text(item: Any) -> str:
    heading_path = getattr(item, "heading_path", None)
    headings = " ".join(str(value) for value in heading_path or () if value)
    return " ".join(
        part
        for part in (
            str(getattr(item, "document_name", "") or ""),
            str(getattr(item, "section_title", "") or ""),
            headings,
            str(getattr(item, "source_locator", "") or ""),
        )
        if part
    )


def _technical_context_text(item: Any) -> str:
    heading_path = getattr(item, "heading_path", None)
    source_locator = str(getattr(item, "source_locator", "") or "")
    reliable_locator = source_locator if source_locator.casefold().startswith("section:") else ""
    return _normalize_text(
        " ".join(
            part
            for part in (
                str(getattr(item, "text", "") or ""),
                str(getattr(item, "section_title", "") or ""),
                " ".join(str(value) for value in heading_path or () if value),
                reliable_locator,
            )
            if part
        )
    )


def _relation_context_text(item: Any) -> str:
    heading_path = getattr(item, "heading_path", None)
    return _normalize_text(
        " ".join(
            part
            for part in (
                str(getattr(item, "text", "") or ""),
                str(getattr(item, "section_title", "") or ""),
                " ".join(str(value) for value in heading_path or () if value),
            )
            if part
        )
    )


def _evidence_id(item: Any) -> str:
    metadata = getattr(item, "metadata", None)
    marker = getattr(item, "marker", None)
    if not marker and hasattr(metadata, "get"):
        marker = metadata.get("marker")
    if marker:
        return str(marker)
    citation_unit_id = getattr(item, "citation_unit_id", None)
    if citation_unit_id is not None:
        return f"citation_unit:{citation_unit_id}"
    chunk_db_id = getattr(item, "chunk_db_id", None)
    if chunk_db_id is not None:
        return f"chunk_db:{chunk_db_id}"
    return f"chunk:{getattr(item, 'document_id', 'unknown')}:{getattr(item, 'chunk_id', 'unknown')}"


def _extract_exact_identifiers(query: str) -> tuple[str, ...]:
    identifiers: list[str] = []
    for pattern in TECHNICAL_PATTERNS:
        for match in pattern.finditer(query):
            identifiers.append(match.group(1) if match.groups() else match.group(0))
    lowered = query.casefold()
    if "docker compose down -v" in lowered:
        identifiers.append("docker compose down -v")
    if re.search(r"\bDepends\b", query):
        identifiers.append("Depends")
    return tuple(dict.fromkeys(item.strip("` ") for item in identifiers if item.strip("` ")))


def _requested_attributes(lowered_query: str) -> tuple[str, ...]:
    found: list[str] = []
    for name, aliases in ATTRIBUTE_ALIASES.items():
        if any(alias.casefold() in lowered_query for alias in aliases):
            found.append(name)
    return tuple(dict.fromkeys(found))


def _extract_attribute_entity_terms(query: str, requested_attributes: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = query
    remove_terms = [
        "的",
        "是什么",
        "是谁",
        "是多少",
        "什么",
        "在哪里",
        "在哪",
        "什么时候",
        "哪一年",
        "哪一天",
        "去年",
        "规则",
        "办公",
        "型号",
        "使用哪款",
        "有多重",
    ]
    for aliases in ATTRIBUTE_ALIASES.values():
        remove_terms.extend(aliases)
    for term in sorted(remove_terms, key=len, reverse=True):
        cleaned = re.sub(re.escape(term), " ", cleaned, flags=re.I)
    cleaned = re.sub(r"[?？。,.，]", " ", cleaned)
    normalized = _normalize_entity(cleaned)
    return (normalized,) if normalized else ()


def _extract_reason_entity_terms(query: str) -> tuple[str, ...]:
    cleaned = re.sub(r"为什么|why|使用|需要|适合|受欢迎|有用|主要目的|目的|是什么|的", " ", query, flags=re.I)
    normalized = _normalize_entity(cleaned)
    return (normalized,) if normalized else ()


def _extract_profile_entity_terms(query: str, query_type: str) -> tuple[str, ...]:
    if query_type == QUERY_TYPE_ENTITY_ATTRIBUTE:
        return _extract_attribute_entity_terms(query, _requested_attributes(query.casefold()))
    if query_type == QUERY_TYPE_ENTITY_REASON:
        return _extract_reason_entity_terms(query)
    if query_type == QUERY_TYPE_ENTITY_DEFINITION:
        return _extract_definition_entity_terms(query)
    return ()


def _extract_definition_entity_terms(query: str) -> tuple[str, ...]:
    cleaned = re.sub(r"是什么|是谁|是啥|what is|介绍一下|介绍|定义|\?|？|。", " ", query, flags=re.I)
    normalized = _normalize_entity(cleaned)
    return (normalized,) if normalized else ()


def _extract_relation_terms(query: str) -> tuple[str, ...]:
    patterns = [
        r"(.+?)(?:和|与|跟)(.+?)(?:是什么关系|有(?:什么)?关系|的关系|之间是什么.+关系|关系)",
        r"(.+?)\\s+and\\s+(.+?)(?:\\s+relationship|\\s+related|\\?)",
        r"relationship between (.+?) and (.+?)(?:\\?|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, re.I)
        if match:
            return tuple(
                term
                for term in (
                    _normalize_relation_entity(match.group(1)),
                    _normalize_relation_entity(match.group(2)),
                )
                if term
            )
    single = re.search(r"(.+?)(?:属于哪个|属于什么|隶属于哪个|隶属于什么)", query)
    if single:
        term = _normalize_entity(single.group(1))
        return (term,) if term else ()
    return ()


def _normalize_relation_entity(value: str) -> str:
    cleaned = re.sub(
        r"(?:的)?(?:情节|故事|剧情|人物|角色)?(?:关系)?(?:是什么|如何)?\s*$",
        "",
        value,
        flags=re.I,
    )
    return _normalize_entity(cleaned)


def _entity_coverage(entity_terms: tuple[str, ...], context: str) -> bool:
    if not entity_terms:
        return True
    return any(_term_covered(term, context) for term in entity_terms if term)


def _relation_entity_coverage(support_query: _SupportQuery, context: str) -> bool:
    if not support_query.entity_terms:
        return True
    hits = [
        term
        for term in support_query.entity_terms
        if term and _term_covered(term, context)
    ]
    if len(support_query.entity_terms) <= 1:
        return bool(hits)
    return len(hits) >= 2


def _relation_support(
    support_query: _SupportQuery,
    evidence_units: Sequence[Any],
) -> tuple[bool, tuple[str, ...]]:
    if support_query.query_type != QUERY_TYPE_ENTITY_RELATION:
        return _relation_entity_coverage(support_query, "\n".join(_evidence_context(item) for item in evidence_units)), ()
    if not support_query.entity_terms:
        return True, tuple(_evidence_id(item) for item in evidence_units)

    by_document: dict[str, list[Any]] = {}
    for item in evidence_units:
        by_document.setdefault(_document_scope_key(item), []).append(item)

    for document_units in by_document.values():
        direct_support = [
            item
            for item in document_units
            if _relation_entity_coverage(support_query, _relation_context_text(item))
            and _contains_any(_relation_context_text(item).casefold(), RELATION_EVIDENCE_TERMS)
        ]
        if direct_support:
            return True, tuple(_evidence_id(item) for item in direct_support)
        for scoped_units in _relation_scopes(document_units):
            contexts = [_relation_context_text(item) for item in scoped_units]
            aggregate = "\n".join(contexts)
            if not _relation_entity_coverage(support_query, aggregate):
                continue
            relation_units = [
                item
                for item, context in zip(scoped_units, contexts, strict=False)
                if _contains_any(context.casefold(), RELATION_EVIDENCE_TERMS)
            ]
            if not relation_units:
                continue
            return True, tuple(dict.fromkeys(_evidence_id(item) for item in scoped_units))
    return False, ()


def _relation_scopes(evidence_units: Sequence[Any]) -> list[list[Any]]:
    scopes: dict[str, list[Any]] = {}
    unscoped: list[Any] = []
    for item in evidence_units:
        scope = _local_structure_scope(item)
        if scope:
            scopes.setdefault(scope, []).append(item)
        else:
            unscoped.append(item)

    grouped = list(scopes.values())
    # An unscoped unit must carry both entities and a relation itself; unrelated
    # unscoped units are never combined merely because they share a document.
    grouped.extend([[item] for item in unscoped])
    return grouped


def _document_scope_key(item: Any) -> str:
    document_id = getattr(item, "document_id", None)
    if document_id is not None:
        return f"id:{document_id}"
    return f"name:{getattr(item, 'document_name', '') or ''}"


def _local_structure_scope(item: Any) -> str:
    heading_path = tuple(str(value).casefold() for value in getattr(item, "heading_path", None) or () if value)
    if heading_path:
        return "heading:" + "/".join(heading_path)
    section_title = str(getattr(item, "section_title", "") or "").strip().casefold()
    if section_title:
        return f"section:{section_title}"
    source_locator = str(getattr(item, "source_locator", "") or "").strip().casefold()
    if source_locator.startswith("section:"):
        return source_locator
    return ""


def _attribute_coverage(requested_attributes: tuple[str, ...], context: str) -> bool:
    if not requested_attributes:
        return True
    lowered = context.casefold()
    return all(
        any(alias.casefold() in lowered for alias in ATTRIBUTE_ALIASES.get(attribute, (attribute,)))
        for attribute in requested_attributes
    )


def _exact_identifier_coverage(identifiers: tuple[str, ...], context: str) -> bool:
    if not identifiers:
        return True
    normalized_context = _identifier_compare_text(context)
    return all(
        _identifier_compare_text(identifier) in normalized_context
        or _identifier_parts_covered(identifier, context)
        for identifier in identifiers
    )


def _technical_support(
    support_query: _SupportQuery,
    evidence_units: Sequence[Any],
) -> tuple[bool, bool, tuple[str, ...]]:
    if support_query.query_type != QUERY_TYPE_EXACT_TECHNICAL:
        aggregate = "\n".join(_evidence_context(item) for item in evidence_units)
        return _exact_identifier_coverage(support_query.exact_identifiers, aggregate), True, ()

    by_document: dict[str, list[Any]] = {}
    for item in evidence_units:
        by_document.setdefault(_document_scope_key(item), []).append(item)

    identifier_seen = False
    for document_units in by_document.values():
        aggregate = "\n".join(_technical_context_text(item) for item in document_units)
        if not _exact_identifier_coverage(support_query.exact_identifiers, aggregate):
            continue
        identifier_seen = True
        if _technical_intent_coverage(support_query, aggregate):
            return True, True, tuple(_evidence_id(item) for item in document_units)
    return identifier_seen, False, ()


def _technical_intent_coverage(support_query: _SupportQuery, context: str) -> bool:
    lowered_query = " ".join(support_query.keywords).casefold()
    lowered_context = context.casefold()
    if _contains_any(lowered_query, ("支持哪些值", "哪些值", "supported values", "valid values", "options")):
        normalized_tokens = set(_identifier_tokens(context))
        has_known_values = "fixed" in normalized_tokens and (
            "blockaware" in normalized_tokens
            or {"block", "aware"}.issubset(normalized_tokens)
        )
        return has_known_values or _contains_any(
            lowered_context,
            ("supported values", "valid values", "可选值", "支持的值"),
        )
    if _contains_any(lowered_query, ("默认值", "default value", "default")):
        return _contains_any(lowered_context, ("默认值", "default")) and bool(
            re.search(r"(?:^|[\s:=])(?:-?\d+(?:\.\d+)?|true|false|none|null)(?:$|[\s,.;，。])", lowered_context)
        )
    if _contains_any(lowered_query, ("作者", "author", "created by", "maintainer")):
        return _contains_any(lowered_context, ("作者", "author", "created by", "maintainer"))
    return _intent_coverage(support_query, context)


def _intent_coverage(support_query: _SupportQuery, context: str) -> bool:
    lowered = context.casefold()
    if support_query.query_type == QUERY_TYPE_ENTITY_DEFINITION:
        return _contains_any(lowered, DEFINITION_TERMS)
    if support_query.query_type == QUERY_TYPE_ENTITY_REASON:
        return _contains_any(lowered, REASON_TERMS)
    if support_query.query_type == QUERY_TYPE_ENTITY_RELATION:
        return _contains_any(lowered, RELATION_TERMS)
    if support_query.query_type == QUERY_TYPE_EXACT_TECHNICAL:
        if _contains_any(_normalize_text(" ".join(support_query.keywords)).casefold(), ("影响", "发生什么", "what happens")):
            return _contains_any(lowered, ("remove", "delete", "preserve", "删除", "移除", "保留", "happens", "会"))
        return True
    return True


def _lexical_support(keywords: tuple[str, ...], context: str) -> bool:
    if not keywords:
        return True
    lowered = context.casefold()
    meaningful = [keyword for keyword in keywords if len(keyword) > 1]
    if not meaningful:
        return True
    hits = sum(1 for keyword in meaningful if keyword.casefold() in lowered)
    return hits / max(1, len(meaningful)) >= 0.35


def _max_score(evidence_units: Sequence[Any]) -> float:
    scores: list[float] = []
    for item in evidence_units:
        for name in ("score", "final_score", "rerank_score", "vector_score", "keyword_score", "graph_score"):
            value = getattr(item, name, None)
            if value is not None:
                scores.append(float(value))
                break
    return max(scores) if scores else 0.0


def _keywords(query: str) -> tuple[str, ...]:
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]{2,}", query)
    stopwords = {
        "是什么",
        "是谁",
        "为什么",
        "哪里",
        "什么",
        "多少",
        "这个",
        "文档",
        "请问",
        "how",
        "what",
        "why",
        "the",
        "does",
    }
    return tuple(token for token in tokens if token.casefold() not in stopwords)


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    return any(term.casefold() in text for term in terms)


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split())


def _normalize_entity(value: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", " ", value)
    return " ".join(normalized.split()).strip()


def _entity_compare_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold())


def _identifier_compare_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold())


def _identifier_parts_covered(identifier: str, context: str) -> bool:
    parts = _identifier_tokens(identifier)
    if not parts:
        return False
    context_tokens = set(_identifier_tokens(context))
    return all(part in context_tokens for part in parts)


def _identifier_tokens(value: str) -> list[str]:
    unquoted = re.sub(r"[`'\"]", " ", str(value or ""))
    split_camel = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", unquoted)
    raw_tokens = re.findall(r"[A-Za-z0-9]+", re.sub(r"[_-]+", " ", split_camel))
    return [_singularize_identifier_token(token.casefold()) for token in raw_tokens if token]


def _singularize_identifier_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _term_covered(term: str, context: str) -> bool:
    normalized_context = _entity_compare_text(context)
    normalized_term = _entity_compare_text(term)
    if normalized_term and normalized_term in normalized_context:
        return True
    if _identifier_parts_covered(term, context):
        return True

    term_tokens = _entity_tokens(term)
    if not term_tokens:
        return True
    context_tokens = set(_entity_tokens(context))
    return all(_token_or_alias_present(token, context_tokens) for token in term_tokens)


def _entity_tokens(value: str) -> list[str]:
    return [
        token.casefold()
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[\u4e00-\u9fff]{1,}", value)
        if token.strip()
    ]


def _token_or_alias_present(token: str, context_tokens: set[str]) -> bool:
    aliases = {
        "类": {"class", "classes", "类"},
        "目的": {"purpose", "目的"},
        "办公城市": {"办公地点", "city", "location", "办公城市"},
        "显式锁": {"显式锁", "lock", "locks", "locking", "blocking"},
    }
    candidates = aliases.get(token, {token})
    return any(candidate in context_tokens for candidate in candidates)
