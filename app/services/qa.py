from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
import logging
import re
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.document import Document
from app.models.document_citation_unit import DocumentCitationUnit
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.schemas.llm import (
    DEEPSEEK_PROVIDER,
    HEURISTIC_PROVIDER,
    OPENAI_COMPATIBLE_PROVIDER,
)
from app.schemas.qa import CitationRead
from app.services.chunk_metadata import build_chunk_snippet, parse_chunk_metadata
from app.services.document_embedding import RetrievedChunk, tokenize_text
from app.services.evidence_support import (
    OVERVIEW_INTENT,
    EvidenceSupportDecision,
    evaluate_evidence_support,
)
from app.services.llm import LLMProviderError, generate_openai_compatible_chat_completion
from app.services.overview_retrieval import collect_overview_chunks
from app.services.qa_intent import QAIntent, classify_qa_intent
from app.services.retrieval import trace_service
from app.services.retrieval.types import RetrievalMode, RetrievalResult
from app.services.source_locator import (
    build_preview_target_for_chunk,
    build_source_locator_for_chunk,
)


NO_RELIABLE_EVIDENCE_MESSAGE = "当前知识库中没有找到足够可靠的依据，无法确认该问题。"
MAX_ASK_CONTEXT_CHUNKS = 6
MAX_ASK_CONTEXT_TOTAL_CHARS = 4200
MAX_ASK_CHUNKS_PER_DOCUMENT = 2
MAX_ASK_EVIDENCE_UNITS = 8
MAX_EVIDENCE_UNITS_PER_CHUNK = 2
RANGE_OVERLAP_THRESHOLD = 0.6
TOKEN_JACCARD_THRESHOLD = 0.9
WHITESPACE_PATTERN = re.compile(r"\s+")
CITATION_MARKER_PATTERN = re.compile(r"\[((?:\s*[Ss]?\d+\s*(?:,\s*[Ss]?\d+\s*)*))\]")
CHINESE_CHARACTER_PATTERN = re.compile(r"[\u4e00-\u9fff]")
PREFERRED_EVIDENCE_ENDING_CHARACTERS = {"。", "！", "？", "；", ".", "!", "?", ";", "…", ")", "）", "]", "】", "\"", "”"}

QUERY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "长啥样": ("外貌", "外形", "样子", "特征"),
    "长什么样": ("外貌", "外形", "样子", "特征"),
    "是什么": ("定义", "含义", "介绍"),
    "是谁": ("身份", "人物", "角色", "介绍", "定义"),
    "为什么受欢迎": ("原因", "受欢迎", "人气", "吸引力", "因素"),
    "为什么火": ("原因", "受欢迎", "人气", "吸引力", "因素"),
    "什么关系": ("关系", "关联", "依赖", "连接", "朋友", "伙伴", "合作"),
    "在哪里": ("地点", "位置", "办公地点"),
    "在哪": ("地点", "位置", "办公地点"),
    "怎么做": ("方法", "步骤", "流程"),
    "有什么用": ("作用", "用途", "功能"),
    "怎么保证": ("可靠性", "保证", "机制", "设计"),
}

ENTITY_QUERY_TYPES = {
    "entity_definition",
    "entity_attribute",
    "entity_reason",
    "entity_relation",
}
ENTITY_PER_CHUNK_LIMIT_TYPES = {
    "entity_definition",
    "entity_attribute",
    "entity_reason",
}
ENTITY_MAX_EVIDENCE_UNITS = 3
ENTITY_CONTEXT_QUERY_TYPES = {
    "entity_definition",
    "entity_attribute",
    "entity_reason",
}
ENTITY_CONTEXT_MIN_LEXICAL_RELEVANCE = 0.05
ENTITY_FOLLOWUP_MIN_LEXICAL_RELEVANCE = 0.15
ENTITY_FOLLOWUP_STRONG_LEXICAL_RELEVANCE = 0.40
ENTITY_FOLLOWUP_MIN_RELATIVE_SCORE = 0.70
SAME_CHUNK_ENTITY_FOLLOWUP_MIN_LEXICAL_RELEVANCE = 0.30

ENTITY_DEFINITION_TERMS = frozenset(
    {
        "身份",
        "人物",
        "角色",
        "定义",
        "介绍",
        "职业",
        "产品",
        "项目",
        "工具",
        "系统",
        "组织",
        "概念",
    }
)
ENTITY_ATTRIBUTE_TERMS = frozenset(
    {
        "属性",
        "外貌",
        "外形",
        "外型",
        "形态",
        "结构",
        "样子",
        "颜色",
        "尺寸",
        "重量",
        "特征",
        "特点",
        "配置",
        "规格",
        "地点",
        "位置",
        "办公地点",
    }
)
ENTITY_REASON_TERMS = frozenset(
    {
        "原因",
        "为什么",
        "优势",
        "影响",
        "受欢迎",
        "人气",
        "吸引力",
        "因素",
        "特点",
    }
)
ENTITY_RELATION_TERMS = frozenset(
    {
        "关系",
        "关联",
        "依赖",
        "朋友",
        "伙伴",
        "合作",
        "同事",
        "成员",
        "隶属",
        "属于",
        "包含",
        "调用",
        "负责",
        "权限",
        "上下游",
        "连接",
        "组成",
        "derived from",
        "depends on",
        "works with",
        "follows",
        "followed",
        "leads",
        "encounters",
        "produces",
        "becomes",
        "creates",
        "reduces",
        "supports",
        "without blocking",
    }
)

logger = logging.getLogger("purelink.qa")


class AnswerGenerationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PromptBundle:
    system_prompt: str
    user_prompt: str
    rendered_prompt: str


@dataclass(frozen=True, slots=True)
class QuestionAnswerResult:
    answer: str
    citations: list[CitationRead]
    prompt: PromptBundle
    intent: str
    evidence_support: EvidenceSupportDecision | None = None


@dataclass(frozen=True, slots=True)
class MessageContext:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class CitationUnitCandidate:
    marker: str
    citation_id: int | None
    citation_unit_id: int | None
    chunk_db_id: int | None
    chunk_id: str
    document_id: int
    knowledge_base_id: int
    scope: str
    team_id: int | None
    document_name: str
    text: str
    snippet: str
    source_type: str | None
    char_start: int | None
    char_end: int | None
    page_number: int | None
    start_time: float | None
    end_time: float | None
    section_title: str | None
    source_locator: str | None
    heading_path: tuple[str, ...] | None
    lexical_relevance: float
    score: float
    entity_exact_match: bool = False
    entity_context_match: bool = False
    intent_alignment: float = 0.0


@dataclass(frozen=True, slots=True)
class QueryEvidenceProfile:
    query_type: str
    entity_terms: frozenset[str]
    intent_terms: frozenset[str]

    @property
    def is_entity_query(self) -> bool:
        return self.query_type in ENTITY_QUERY_TYPES


class AnswerGenerator(Protocol):
    def generate(
        self,
        *,
        question: str,
        evidence_units: list[CitationUnitCandidate],
        prompt: PromptBundle,
    ) -> str: ...


class HeuristicAnswerGenerator:
    def generate(
        self,
        *,
        question: str,
        evidence_units: list[CitationUnitCandidate],
        prompt: PromptBundle,
    ) -> str:
        if not evidence_units:
            return NO_RELIABLE_EVIDENCE_MESSAGE

        snippets = [
            f"{_compress_text(item.text)} [{item.marker}]"
            for item in evidence_units[:2]
        ]
        return "根据当前知识库证据，" + " ".join(snippets)


class OpenAICompatibleAnswerGenerator:
    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 30.0,
        reasoning_effort: str | None = None,
        thinking_enabled: bool = False,
    ) -> None:
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.reasoning_effort = reasoning_effort
        self.thinking_enabled = thinking_enabled

    def generate(
        self,
        *,
        question: str,
        evidence_units: list[CitationUnitCandidate],
        prompt: PromptBundle,
    ) -> str:
        try:
            return generate_openai_compatible_chat_completion(
                api_base=self.api_base,
                api_key=self.api_key,
                model=self.model,
                system_prompt=prompt.system_prompt,
                user_prompt=prompt.user_prompt,
                timeout=self.timeout_seconds,
                reasoning_effort=self.reasoning_effort,
                thinking_enabled=self.thinking_enabled,
            )
        except LLMProviderError as exc:
            raise AnswerGenerationError(str(exc)) from exc


def answer_question(
    *,
    db: Session | None = None,
    question: str,
    retrieved_chunks: list[RetrievedChunk],
    documents: Sequence[Document] | None = None,
    knowledge_base_id: int | None = None,
    scope: KnowledgeBaseScope | None = None,
    required_review_status: DocumentReviewStatus | None = None,
    team_id: int | None = None,
    conversation_context: list[MessageContext] | None = None,
    retrieval_query: str | None = None,
    retrieval_result: RetrievalResult | None = None,
    generator: AnswerGenerator | None = None,
    settings: Settings | None = None,
) -> QuestionAnswerResult:
    active_settings = settings or get_settings()
    intent = classify_qa_intent(question)
    logger.info(
        "qa intent resolved knowledge_base_id=%s question=%s qa_intent=%s retrieved_chunk_count=%s",
        knowledge_base_id,
        question,
        intent.value,
        len(retrieved_chunks),
    )
    if retrieval_result is not None:
        context_chunks = retrieval_result.metadata.get("context_chunks") or []
        evidence_units = retrieval_result.metadata.get("evidence_units") or None
        retrieval_intent = (
            QAIntent.KB_OVERVIEW
            if retrieval_result.mode == RetrievalMode.OVERVIEW
            else QAIntent.KB_FACT_QA
        )
        return _answer_with_context_chunks(
            db=db,
            question=question,
            context_chunks=context_chunks,
            intent=retrieval_intent,
            conversation_context=conversation_context,
            retrieval_query=retrieval_query,
            generator=generator,
            settings=active_settings,
            preselected_evidence_units=evidence_units,
            retrieval_result=retrieval_result,
        )

    if intent == QAIntent.KB_OVERVIEW:
        return _answer_kb_overview_question(
            db=db,
            question=question,
            retrieved_chunks=retrieved_chunks,
            documents=documents,
            knowledge_base_id=knowledge_base_id,
            scope=scope,
            required_review_status=required_review_status,
            team_id=team_id,
            conversation_context=conversation_context,
            retrieval_query=retrieval_query,
            generator=generator,
            settings=active_settings,
        )

    return _answer_kb_fact_question(
        db=db,
        question=question,
        retrieved_chunks=retrieved_chunks,
        conversation_context=conversation_context,
        retrieval_query=retrieval_query,
        generator=generator,
        settings=active_settings,
    )


def _answer_kb_fact_question(
    *,
    db: Session | None,
    question: str,
    retrieved_chunks: list[RetrievedChunk],
    conversation_context: list[MessageContext] | None,
    retrieval_query: str | None,
    generator: AnswerGenerator | None,
    settings: Settings,
) -> QuestionAnswerResult:
    context_chunks = select_context_chunks_for_answer(retrieved_chunks)
    return _answer_with_context_chunks(
        db=db,
        question=question,
        context_chunks=context_chunks,
        intent=QAIntent.KB_FACT_QA,
        conversation_context=conversation_context,
        retrieval_query=retrieval_query,
        generator=generator,
        settings=settings,
        preselected_evidence_units=None,
        retrieval_result=None,
    )


def _answer_kb_overview_question(
    *,
    db: Session | None,
    question: str,
    retrieved_chunks: list[RetrievedChunk],
    documents: Sequence[Document] | None,
    knowledge_base_id: int | None,
    scope: KnowledgeBaseScope | None,
    required_review_status: DocumentReviewStatus | None,
    team_id: int | None,
    conversation_context: list[MessageContext] | None,
    retrieval_query: str | None,
    generator: AnswerGenerator | None,
    settings: Settings,
) -> QuestionAnswerResult:
    if (
        db is None
        or documents is None
        or knowledge_base_id is None
        or scope is None
        or required_review_status is None
    ):
        logger.info(
            "qa overview fallback question=%s reason=%s",
            question,
            "missing_database_or_document_context",
        )
        return _answer_kb_fact_question(
            db=db,
            question=question,
            retrieved_chunks=retrieved_chunks,
            conversation_context=conversation_context,
            retrieval_query=retrieval_query,
            generator=generator,
            settings=settings,
        )

    context_chunks = collect_overview_chunks(
        db=db,
        documents=documents,
        knowledge_base_id=knowledge_base_id,
        scope=scope,
        required_review_status=required_review_status,
        team_id=team_id,
        max_chunks=settings.overview_max_chunks,
        max_chunks_per_document=settings.overview_max_chunks_per_document,
    )
    indexed_document_count = sum(
        1
        for item in documents
        if item.review_status == required_review_status
        and item.processing_status == DocumentProcessingStatus.INDEXED
    )
    logger.info(
        "qa overview chunks collected knowledge_base_id=%s question=%s indexed_document_count=%s overview_chunk_count=%s",
        knowledge_base_id,
        question,
        indexed_document_count,
        len(context_chunks),
    )
    return _answer_with_context_chunks(
        db=db,
        question=question,
        context_chunks=context_chunks,
        intent=QAIntent.KB_OVERVIEW,
        conversation_context=conversation_context,
        retrieval_query=retrieval_query,
        generator=generator,
        settings=settings,
        preselected_evidence_units=None,
        retrieval_result=None,
    )


def _answer_with_context_chunks(
    *,
    db: Session | None,
    question: str,
    context_chunks: list[RetrievedChunk],
    intent: QAIntent,
    conversation_context: list[MessageContext] | None,
    retrieval_query: str | None,
    generator: AnswerGenerator | None,
    settings: Settings,
    preselected_evidence_units: list[CitationUnitCandidate] | None,
    retrieval_result: RetrievalResult | None,
) -> QuestionAnswerResult:
    evidence_profile = _build_query_evidence_profile(question)
    if preselected_evidence_units is None:
        chunk_units = load_citation_units_for_chunks(db=db, chunks=context_chunks) if db is not None else {}
        evidence_units = select_evidence_units(
            question=question,
            retrieved_chunks=context_chunks,
            chunk_units=chunk_units,
            max_evidence_units=max(MAX_ASK_EVIDENCE_UNITS, settings.max_citations),
            use_query_evidence_profile=intent != QAIntent.KB_OVERVIEW,
        )
    else:
        evidence_units = preselected_evidence_units
    logger.info(
        "qa evidence selected question=%s qa_intent=%s selected_chunk_ids=%s candidate_evidence_unit_count=%s fallback_chunk_citation_count=%s evidence_content_lengths=%s",
        question,
        intent.value,
        [item.chunk_id for item in context_chunks],
        len(evidence_units),
        sum(1 for item in evidence_units if item.citation_unit_id is None),
        [len(item.text) for item in evidence_units],
    )
    support_decision = evaluate_evidence_support(
        query=question,
        evidence_units=evidence_units,
        profile=evidence_profile,
        qa_intent=OVERVIEW_INTENT if intent == QAIntent.KB_OVERVIEW else None,
    )
    _record_evidence_support_metadata(
        db=db,
        retrieval_result=retrieval_result,
        support_decision=support_decision,
    )
    prompt = (
        build_overview_prompt(
            question=question,
            evidence_units=evidence_units,
            conversation_context=conversation_context,
        )
        if intent == QAIntent.KB_OVERVIEW
        else build_fact_prompt(
            question=question,
            evidence_units=evidence_units,
            conversation_context=conversation_context,
        )
    )
    has_reliable_context = (
        bool(evidence_units)
        if intent == QAIntent.KB_OVERVIEW
        else _has_reliable_retrieval_results(
            context_chunks,
            min_score=settings.retrieval_min_score,
        ) and bool(evidence_units)
    )
    if not has_reliable_context or not support_decision.answerable:
        answer = NO_RELIABLE_EVIDENCE_MESSAGE
        citations: list[CitationRead] = []
        skip_reason = (
            "insufficient_retrieval_or_evidence"
            if not has_reliable_context
            else support_decision.reason
        )
        logger.info(
            "qa answer skipped question=%s qa_intent=%s selected_chunk_ids=%s reason=%s support_score=%s",
            question,
            intent.value,
            [item.chunk_id for item in context_chunks],
            skip_reason,
            support_decision.support_score,
        )
    else:
        answer_generator = generator or resolve_answer_generator(settings)
        answer = answer_generator.generate(
            question=question,
            evidence_units=evidence_units,
            prompt=prompt,
        )
        used_markers = extract_used_citation_ids(answer)
        answer = normalize_answer_citation_markers(
            answer_text=answer,
            allowed_markers={item.marker for item in evidence_units},
        )
        if not used_markers:
            answer = NO_RELIABLE_EVIDENCE_MESSAGE
            citations = []
            logger.info(
                "qa answer rejected question=%s qa_intent=%s used_marker_ids=%s reason=%s",
                question,
                intent.value,
                used_markers,
                "no_valid_citation_markers",
            )
        else:
            citations = build_answer_citations(
                evidence_units=evidence_units,
                used_markers=used_markers,
                max_citations=settings.max_citations,
            )
            if not citations:
                answer = NO_RELIABLE_EVIDENCE_MESSAGE
            logger.info(
                "qa citations resolved question=%s qa_intent=%s used_marker_ids=%s used_citation_unit_ids=%s fallback_chunk_citation_count=%s returned_citation_count=%s",
                question,
                intent.value,
                used_markers,
                [item.citation_unit_id for item in citations if item.citation_unit_id is not None],
                sum(1 for item in citations if item.citation_unit_id is None),
                len(citations),
            )
    return QuestionAnswerResult(
        answer=answer,
        citations=citations,
        prompt=prompt,
        intent=intent.value,
        evidence_support=support_decision,
    )


def _record_evidence_support_metadata(
    *,
    db: Session | None,
    retrieval_result: RetrievalResult | None,
    support_decision: EvidenceSupportDecision,
) -> None:
    metadata = support_decision.to_metadata()
    if retrieval_result is not None:
        retrieval_result.metadata.update(metadata)
    if db is None or retrieval_result is None or retrieval_result.trace_id is None:
        return
    try:
        trace_service.merge_retrieval_trace_metadata(
            db,
            trace_id=int(retrieval_result.trace_id),
            metadata=metadata,
        )
    except Exception:
        logger.exception("failed to record evidence support metadata trace_id=%s", retrieval_result.trace_id)


def build_conversation_context(
    *,
    messages: Sequence[object],
    max_total_chars: int,
    max_message_chars: int,
) -> list[MessageContext]:
    contexts_reversed: list[MessageContext] = []
    total_chars = 0

    for message in reversed(messages):
        raw_content = str(getattr(message, "content", "") or "").strip()
        if not raw_content:
            continue

        role = str(getattr(message, "role", "") or "").lower()
        if role not in {"user", "assistant"}:
            continue

        content = _trim_text_for_prompt(raw_content, max_chars=max_message_chars)
        if not content:
            continue

        remaining_chars = max_total_chars - total_chars
        if remaining_chars <= 0:
            break
        if len(content) > remaining_chars:
            content = _trim_text_for_prompt(content, max_chars=remaining_chars)
        if not content:
            break

        contexts_reversed.append(MessageContext(role=role, content=content))
        total_chars += len(content)

    contexts_reversed.reverse()
    return contexts_reversed


def build_conversation_retrieval_query(
    *,
    question: str,
    recent_messages: Sequence[MessageContext],
) -> str:
    selected_user_messages = [
        item.content
        for item in recent_messages
        if item.role == "user"
    ][-2:]
    last_assistant_message = next(
        (item.content for item in reversed(recent_messages) if item.role == "assistant"),
        None,
    )

    parts: list[str] = []
    parts.extend(selected_user_messages)
    if last_assistant_message:
        parts.append(
            _trim_text_for_prompt(
                _strip_citation_markers(last_assistant_message),
                max_chars=200,
            )
        )
    parts.append(question.strip())

    seen: set[str] = set()
    deduped_parts: list[str] = []
    for part in parts:
        normalized = _normalize_text(part)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped_parts.append(part.strip())

    return "\n".join(deduped_parts)


def _has_reliable_retrieval_results(
    retrieved_chunks: list[RetrievedChunk],
    *,
    min_score: float,
) -> bool:
    if not retrieved_chunks:
        return False
    top_score = max(chunk.score for chunk in retrieved_chunks)
    return top_score >= max(0.0, min_score)


def select_context_chunks_for_answer(
    retrieved_chunks: list[RetrievedChunk],
    *,
    question: str | None = None,
    max_chunks: int = MAX_ASK_CONTEXT_CHUNKS,
    max_total_chars: int = MAX_ASK_CONTEXT_TOTAL_CHARS,
    max_chunks_per_document: int = MAX_ASK_CHUNKS_PER_DOCUMENT,
) -> list[RetrievedChunk]:
    selected: list[RetrievedChunk] = []
    per_document_count: dict[int, int] = defaultdict(int)
    per_document_chunks: dict[int, list[RetrievedChunk]] = defaultdict(list)
    seen_chunk_ids: set[str] = set()
    seen_text_fingerprints: set[str] = set()
    total_chars = 0

    ranked_chunks = _rank_context_chunks(retrieved_chunks, question=question)
    for chunk in ranked_chunks:
        if len(selected) >= max_chunks:
            break
        if chunk.chunk_id in seen_chunk_ids:
            continue
        if per_document_count[chunk.document_id] >= max_chunks_per_document:
            continue

        normalized_text = _normalize_text(chunk.text)
        if not normalized_text:
            continue

        text_fingerprint = normalized_text[:320]
        if text_fingerprint in seen_text_fingerprints:
            continue

        if _is_redundant_chunk(chunk, per_document_chunks[chunk.document_id]):
            continue

        next_total_chars = total_chars + len(normalized_text)
        if selected and next_total_chars > max_total_chars:
            continue

        selected.append(chunk)
        per_document_count[chunk.document_id] += 1
        per_document_chunks[chunk.document_id].append(chunk)
        seen_chunk_ids.add(chunk.chunk_id)
        seen_text_fingerprints.add(text_fingerprint)
        total_chars = next_total_chars

    return selected


def _rank_context_chunks(
    chunks: list[RetrievedChunk],
    *,
    question: str | None,
) -> list[RetrievedChunk]:
    if not question:
        return chunks

    question_features = _build_query_features(question)
    profile = _build_query_evidence_profile(question)
    technical_identifiers = _extract_technical_identifiers(question)
    technical_intent = _technical_question_intent(question)
    if (
        profile.query_type == "generic_factual"
        and not (technical_identifiers and technical_intent)
    ):
        return chunks
    ranked: list[tuple[float, int, RetrievedChunk]] = []
    for index, chunk in enumerate(chunks):
        structured_text = _build_chunk_structured_relevance_text(chunk)
        lexical_relevance = _lexical_relevance(chunk.text, question_features)
        structured_relevance = _lexical_relevance(structured_text, question_features)
        entity_match = _has_entity_exact_match(
            f"{chunk.text} {structured_text}",
            profile=profile,
        )
        intent_alignment = _intent_alignment(
            f"{chunk.text} {structured_text}",
            profile=profile,
        )
        structure_phrase_bonus = _structure_phrase_bonus(
            question=question,
            structured_text=structured_text,
        )
        intent_weight = 0.15 if profile.query_type == "entity_relation" else 0.05
        score_weight = 0.25 if profile.query_type == "entity_relation" else 0.35
        priority = (
            (score_weight * max(0.0, float(chunk.score)))
            + (0.35 * lexical_relevance)
            + (0.15 * structured_relevance)
            + (0.10 if entity_match else 0.0)
            + (intent_weight if intent_alignment > 0 else 0.0)
            + structure_phrase_bonus
        )
        ranked.append((priority, index, chunk))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked]


def _build_chunk_structured_relevance_text(chunk: RetrievedChunk) -> str:
    parts = [str(chunk.section_title or "")]
    parts.extend(str(item) for item in chunk.heading_path or () if item)
    if chunk.source_locator and str(chunk.source_locator).casefold().startswith("section:"):
        parts.append(str(chunk.source_locator))
    return " ".join(part for part in parts if part)


def _structure_phrase_bonus(*, question: str, structured_text: str) -> float:
    structure_tokens = set(_technical_identifier_tokens(structured_text))
    if len(structure_tokens) < 2:
        return 0.0
    question_tokens = set(_technical_identifier_tokens(question))
    return 0.10 if structure_tokens.issubset(question_tokens) else 0.0


def organize_citations(
    retrieved_chunks: list[RetrievedChunk],
    *,
    max_citations: int = 6,
) -> list[RetrievedChunk]:
    organized: list[RetrievedChunk] = []
    seen_keys: set[tuple[int, str]] = set()

    for chunk in retrieved_chunks:
        if len(organized) >= max_citations:
            break

        locator_key = chunk.source_locator or chunk.chunk_id
        candidate_key = (chunk.document_id, locator_key)
        if candidate_key in seen_keys:
            continue

        organized.append(chunk)
        seen_keys.add(candidate_key)

    return organized


def build_answer_citations(
    *,
    evidence_units: list[CitationUnitCandidate],
    used_markers: list[str],
    max_citations: int,
) -> list[CitationRead]:
    evidence_by_marker = {item.marker: item for item in evidence_units}
    citations: list[CitationRead] = []
    seen_markers: set[str] = set()

    for marker in used_markers:
        if marker in seen_markers:
            continue
        evidence = evidence_by_marker.get(marker)
        if evidence is None:
            continue
        citations.append(build_citation_read_from_unit(evidence))
        seen_markers.add(marker)
        if len(citations) >= max_citations:
            break

    return citations


def load_citation_units_for_chunks(
    *,
    db: Session,
    chunks: list[RetrievedChunk],
) -> dict[str, list[DocumentCitationUnit]]:
    chunk_db_ids = [item.chunk_db_id for item in chunks if item.chunk_db_id is not None]
    chunk_keys = [item.chunk_id for item in chunks if item.chunk_db_id is None]
    if not chunk_db_ids and not chunk_keys:
        return {}
    units_by_chunk: dict[str, list[DocumentCitationUnit]] = defaultdict(list)
    if chunk_db_ids:
        statement = (
            select(DocumentCitationUnit)
            .where(DocumentCitationUnit.chunk_id.in_(chunk_db_ids))
            .order_by(
                DocumentCitationUnit.document_id.asc(),
                DocumentCitationUnit.unit_index.asc(),
            )
        )
        for unit in db.scalars(statement):
            units_by_chunk[unit.chunk_key].append(unit)

    if chunk_keys:
        statement = (
            select(DocumentCitationUnit)
            .where(DocumentCitationUnit.chunk_key.in_(chunk_keys))
            .order_by(
                DocumentCitationUnit.document_id.asc(),
                DocumentCitationUnit.unit_index.asc(),
            )
        )
        for unit in db.scalars(statement):
            units_by_chunk[unit.chunk_key].append(unit)
    return units_by_chunk


def select_evidence_units(
    *,
    question: str,
    retrieved_chunks: list[RetrievedChunk],
    chunk_units: dict[str, list[DocumentCitationUnit]],
    max_evidence_units: int,
    use_query_evidence_profile: bool = True,
) -> list[CitationUnitCandidate]:
    question_features = _build_query_features(question)
    technical_identifiers = _extract_technical_identifiers(question)
    technical_intent = _technical_question_intent(question)
    evidence_profile = (
        _build_query_evidence_profile(question)
        if use_query_evidence_profile
        else QueryEvidenceProfile(
            query_type="generic_factual",
            entity_terms=frozenset(),
            intent_terms=frozenset(),
        )
    )
    if technical_identifiers and technical_intent:
        evidence_profile = QueryEvidenceProfile(
            query_type="generic_factual",
            entity_terms=frozenset(),
            intent_terms=frozenset(),
        )
    per_chunk_limit = (
        1
        if evidence_profile.query_type in ENTITY_PER_CHUNK_LIMIT_TYPES
        else MAX_EVIDENCE_UNITS_PER_CHUNK
    )
    selected: list[CitationUnitCandidate] = []
    seen_keys: set[tuple[int, str, int]] = set()

    for chunk in retrieved_chunks:
        if not use_query_evidence_profile and len(selected) >= max_evidence_units:
            break
        units = chunk_units.get(chunk.chunk_id)
        ranked_units: list[CitationUnitCandidate]
        if units:
            ranked_units = sorted(
                (
                    _build_citation_unit_candidate(
                        unit=unit,
                        chunk=chunk,
                        question_features=question_features,
                        evidence_profile=evidence_profile,
                        technical_identifiers=technical_identifiers,
                        technical_intent=technical_intent,
                    )
                    for unit in units
                ),
                key=lambda item: (-item.score, item.document_id, item.chunk_id, item.citation_unit_id or 0),
            )
        else:
            ranked_units = [
                _build_chunk_fallback_candidate(
                    chunk=chunk,
                    question_features=question_features,
                    evidence_profile=evidence_profile,
                )
            ]

        accepted_count = 0
        for candidate in ranked_units:
            if _should_filter_entity_candidate(candidate, profile=evidence_profile):
                continue
            candidate_key = (candidate.document_id, candidate.chunk_id, candidate.citation_unit_id or -1)
            if candidate_key in seen_keys:
                continue
            selected.append(candidate)
            seen_keys.add(candidate_key)
            accepted_count += 1
            if not use_query_evidence_profile and len(selected) >= max_evidence_units:
                break
            if accepted_count >= per_chunk_limit:
                break

    selected.sort(key=lambda item: (-item.score, item.document_id, item.chunk_id, item.citation_unit_id or -1))
    selected = _apply_entity_evidence_gate(
        selected,
        profile=evidence_profile,
        max_evidence_units=max_evidence_units,
    )
    return [
        CitationUnitCandidate(
            marker=f"S{index}",
            citation_id=item.citation_id,
            citation_unit_id=item.citation_unit_id,
            chunk_db_id=item.chunk_db_id,
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            knowledge_base_id=item.knowledge_base_id,
            scope=item.scope,
            team_id=item.team_id,
            document_name=item.document_name,
            text=item.text,
            snippet=item.snippet,
            source_type=item.source_type,
            char_start=item.char_start,
            char_end=item.char_end,
            page_number=item.page_number,
            start_time=item.start_time,
            end_time=item.end_time,
            section_title=item.section_title,
            source_locator=item.source_locator,
            heading_path=item.heading_path,
            lexical_relevance=item.lexical_relevance,
            score=item.score,
            entity_exact_match=item.entity_exact_match,
            entity_context_match=item.entity_context_match,
            intent_alignment=item.intent_alignment,
        )
        for index, item in enumerate(selected[:max_evidence_units], start=1)
    ]


def _build_citation_unit_candidate(
    *,
    unit: DocumentCitationUnit,
    chunk: RetrievedChunk,
    question_features: set[str],
    evidence_profile: QueryEvidenceProfile,
    technical_identifiers: tuple[str, ...],
    technical_intent: str | None,
) -> CitationUnitCandidate:
    metadata = parse_chunk_metadata(unit.metadata_json, fallback_source_type=chunk.source_type)
    structured_text = _build_bounded_unit_context_text(
        unit_text=unit.unit_text,
        chunk=chunk,
        metadata=metadata,
    )
    lexical_relevance = max(
        _lexical_relevance(unit.unit_text, question_features),
        0.85 * _lexical_relevance(structured_text, question_features),
    )
    relation_scoring_text = (
        structured_text
        if evidence_profile.query_type == "entity_relation"
        else unit.unit_text
    )
    entity_exact_match = _has_entity_exact_match(
        relation_scoring_text,
        profile=evidence_profile,
    )
    intent_alignment = _intent_alignment(
        relation_scoring_text,
        profile=evidence_profile,
    )
    technical_alignment = _technical_evidence_alignment(
        unit_text=unit.unit_text,
        structured_text=structured_text,
        identifiers=technical_identifiers,
        intent=technical_intent,
    )
    entity_context_match = _has_entity_context_match(
        unit_text=unit.unit_text,
        chunk=chunk,
        metadata=metadata,
        lexical_relevance=lexical_relevance,
        intent_alignment=intent_alignment,
        profile=evidence_profile,
    )
    score = _score_evidence_candidate(
        chunk_score=chunk.score,
        lexical_relevance=lexical_relevance,
        entity_exact_match=entity_exact_match,
        entity_context_match=entity_context_match,
        intent_alignment=intent_alignment,
        profile=evidence_profile,
        technical_alignment=technical_alignment,
    )
    return CitationUnitCandidate(
        marker="",
        citation_id=unit.id,
        citation_unit_id=unit.id,
        chunk_db_id=chunk.chunk_db_id or unit.chunk_id,
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        knowledge_base_id=chunk.knowledge_base_id,
        scope=chunk.scope,
        team_id=chunk.team_id,
        document_name=chunk.document_name,
        text=unit.unit_text,
        snippet=build_chunk_snippet(unit.unit_text),
        source_type=metadata.source_type or chunk.source_type,
        char_start=unit.start_char if unit.start_char is not None else metadata.char_start,
        char_end=unit.end_char if unit.end_char is not None else metadata.char_end,
        page_number=metadata.page_number if metadata.page_number is not None else chunk.page_number,
        start_time=metadata.start_time if metadata.start_time is not None else chunk.start_time,
        end_time=metadata.end_time if metadata.end_time is not None else chunk.end_time,
        section_title=metadata.section_title or chunk.section_title,
        source_locator=metadata.source_locator or chunk.source_locator,
        heading_path=metadata.heading_path or chunk.heading_path,
        lexical_relevance=lexical_relevance,
        score=score,
        entity_exact_match=entity_exact_match,
        entity_context_match=entity_context_match,
        intent_alignment=intent_alignment,
    )


def _build_chunk_fallback_candidate(
    *,
    chunk: RetrievedChunk,
    question_features: set[str],
    evidence_profile: QueryEvidenceProfile,
) -> CitationUnitCandidate:
    fallback_text = _resolve_chunk_fallback_text(chunk)
    lexical_relevance = _lexical_relevance(fallback_text, question_features)
    entity_exact_match = _has_entity_exact_match(fallback_text, profile=evidence_profile)
    intent_alignment = _intent_alignment(fallback_text, profile=evidence_profile)
    return CitationUnitCandidate(
        marker="",
        citation_id=None,
        citation_unit_id=None,
        chunk_db_id=chunk.chunk_db_id,
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        knowledge_base_id=chunk.knowledge_base_id,
        scope=chunk.scope,
        team_id=chunk.team_id,
        document_name=chunk.document_name,
        text=fallback_text,
        snippet=build_chunk_snippet(fallback_text),
        source_type=chunk.source_type,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        page_number=chunk.page_number,
        start_time=chunk.start_time,
        end_time=chunk.end_time,
        section_title=chunk.section_title,
        source_locator=chunk.source_locator,
        heading_path=chunk.heading_path,
        lexical_relevance=lexical_relevance,
        score=_score_evidence_candidate(
            chunk_score=chunk.score,
            lexical_relevance=lexical_relevance,
            entity_exact_match=entity_exact_match,
            entity_context_match=False,
            intent_alignment=intent_alignment,
            profile=evidence_profile,
        ),
        entity_exact_match=entity_exact_match,
        intent_alignment=intent_alignment,
    )


def _resolve_chunk_fallback_text(chunk: RetrievedChunk) -> str:
    if chunk.snippet:
        normalized_snippet = _normalize_text(chunk.snippet)
        if normalized_snippet and _looks_like_complete_evidence_text(normalized_snippet):
            return normalized_snippet
    return build_chunk_snippet(chunk.text)


def _looks_like_complete_evidence_text(text: str) -> bool:
    if not text:
        return False
    if text.endswith("..."):
        return False
    return text[-1] in PREFERRED_EVIDENCE_ENDING_CHARACTERS


def _score_evidence_candidate(
    *,
    chunk_score: float,
    lexical_relevance: float,
    entity_exact_match: bool,
    entity_context_match: bool,
    intent_alignment: float,
    profile: QueryEvidenceProfile,
    technical_alignment: float = 0.0,
) -> float:
    if not profile.is_entity_query:
        return min(
            1.0,
            (0.60 * chunk_score)
            + (0.40 * lexical_relevance)
            + (0.10 * technical_alignment),
        )

    entity_score = 1.0 if entity_exact_match or entity_context_match else 0.0
    return (
        (0.50 * chunk_score)
        + (0.25 * lexical_relevance)
        + (0.15 * entity_score)
        + (0.10 * intent_alignment)
    )


def _should_filter_entity_candidate(
    candidate: CitationUnitCandidate,
    *,
    profile: QueryEvidenceProfile,
) -> bool:
    if not profile.is_entity_query:
        return False
    if (
        profile.query_type == "entity_relation"
        and candidate.intent_alignment <= 0
    ):
        return True
    if (
        profile.query_type in {"entity_attribute", "entity_reason"}
        and candidate.citation_unit_id is not None
        and candidate.intent_alignment <= 0
    ):
        return True
    return (
        candidate.lexical_relevance <= 0
        and candidate.intent_alignment <= 0
    )


def _apply_entity_evidence_gate(
    candidates: list[CitationUnitCandidate],
    *,
    profile: QueryEvidenceProfile,
    max_evidence_units: int,
) -> list[CitationUnitCandidate]:
    if not profile.is_entity_query or not candidates:
        return candidates

    top = next(
        (candidate for candidate in candidates if _has_supported_entity_context(candidate)),
        None,
    )
    if top is None:
        return []

    selected = [top]
    limit = (
        max_evidence_units
        if profile.query_type == "entity_relation"
        else min(max_evidence_units, ENTITY_MAX_EVIDENCE_UNITS)
    )
    for candidate in candidates:
        if candidate == top:
            continue
        if len(selected) >= limit:
            break
        if _passes_entity_followup_gate(candidate, top=top, profile=profile):
            selected.append(candidate)
    return selected


def _passes_entity_followup_gate(
    candidate: CitationUnitCandidate,
    *,
    top: CitationUnitCandidate,
    profile: QueryEvidenceProfile,
) -> bool:
    same_chunk = (
        candidate.document_id == top.document_id
        and candidate.chunk_id == top.chunk_id
    )
    if profile.query_type == "entity_relation":
        return (
            _has_supported_entity_context(candidate)
            and (
                candidate.intent_alignment > 0
                or candidate.lexical_relevance >= ENTITY_FOLLOWUP_MIN_LEXICAL_RELEVANCE
            )
            and candidate.score >= (top.score * ENTITY_FOLLOWUP_MIN_RELATIVE_SCORE)
        )
    if same_chunk:
        return (
            _has_supported_entity_context(candidate)
            and candidate.intent_alignment > 0
            and candidate.lexical_relevance
            >= _entity_followup_min_lexical_relevance(
                candidate,
                same_chunk=True,
            )
        )
    return (
        _has_supported_entity_context(candidate)
        and candidate.lexical_relevance
        >= _entity_followup_min_lexical_relevance(
            candidate,
            same_chunk=False,
        )
        and (
            candidate.intent_alignment > 0
            or candidate.lexical_relevance >= ENTITY_FOLLOWUP_STRONG_LEXICAL_RELEVANCE
        )
        and candidate.score >= (top.score * ENTITY_FOLLOWUP_MIN_RELATIVE_SCORE)
    )


def _has_supported_entity_context(candidate: CitationUnitCandidate) -> bool:
    return candidate.entity_exact_match or candidate.entity_context_match


def _entity_followup_min_lexical_relevance(
    candidate: CitationUnitCandidate,
    *,
    same_chunk: bool,
) -> float:
    if candidate.entity_context_match and not candidate.entity_exact_match:
        return ENTITY_CONTEXT_MIN_LEXICAL_RELEVANCE
    if same_chunk:
        return SAME_CHUNK_ENTITY_FOLLOWUP_MIN_LEXICAL_RELEVANCE
    return ENTITY_FOLLOWUP_MIN_LEXICAL_RELEVANCE


def _lexical_relevance(text: str, query_features: set[str]) -> float:
    if not query_features:
        return 0.0
    text_features = _build_text_features(text)
    if not text_features:
        return 0.0
    return len(text_features & query_features) / max(1, len(query_features))


def _build_query_evidence_profile(question: str) -> QueryEvidenceProfile:
    normalized = _normalize_text(question)
    lowered = normalized.lower()

    relation_terms = _extract_relation_entity_terms(normalized)
    if relation_terms:
        return QueryEvidenceProfile(
            query_type="entity_relation",
            entity_terms=frozenset(relation_terms),
            intent_terms=ENTITY_RELATION_TERMS,
        )

    if any(
        pattern in lowered
        for pattern in (
            "长什么样",
            "长啥样",
            "外貌",
            "样子",
            "颜色",
            "重量",
            "尺寸",
            "规格",
            "配置",
            "属性",
            "特点",
            "特征",
            "办公地点",
            "地点",
            "位置",
        )
    ):
        return QueryEvidenceProfile(
            query_type="entity_attribute",
            entity_terms=frozenset(_extract_single_entity_terms(normalized, "entity_attribute")),
            intent_terms=ENTITY_ATTRIBUTE_TERMS,
        )

    if any(pattern in lowered for pattern in ("为什么受欢迎", "为什么这么火", "为什么火", "为什么", "受欢迎")):
        return QueryEvidenceProfile(
            query_type="entity_reason",
            entity_terms=frozenset(_extract_single_entity_terms(normalized, "entity_reason")),
            intent_terms=ENTITY_REASON_TERMS,
        )

    if any(pattern in lowered for pattern in ("是谁", "是什么", "是啥", "介绍", "定义")):
        return QueryEvidenceProfile(
            query_type="entity_definition",
            entity_terms=frozenset(_extract_single_entity_terms(normalized, "entity_definition")),
            intent_terms=ENTITY_DEFINITION_TERMS,
        )

    return QueryEvidenceProfile(
        query_type="generic_factual",
        entity_terms=frozenset(),
        intent_terms=frozenset(),
    )


def build_query_evidence_profile(question: str) -> QueryEvidenceProfile:
    return _build_query_evidence_profile(question)


def _extract_relation_entity_terms(question: str) -> tuple[str, ...]:
    relation_match = re.search(
        r"(.+?)(?:和|与|跟)(.+?)(?:是什么关系|有(?:什么)?关系|的关系|关系)",
        question,
    )
    if relation_match is None:
        return ()
    return tuple(
        term
        for term in (
            _normalize_relation_entity_term(relation_match.group(1)),
            _normalize_relation_entity_term(relation_match.group(2)),
        )
        if term
    )


def _normalize_relation_entity_term(value: str) -> str:
    cleaned = re.sub(
        r"(?:的)?(?:情节|故事|剧情|人物|角色)?(?:关系)?(?:是什么|如何)?\s*$",
        "",
        value,
        flags=re.I,
    )
    return _normalize_entity_term(cleaned)


def _extract_single_entity_terms(question: str, query_type: str) -> tuple[str, ...]:
    cleanup_patterns = {
        "entity_definition": (
            "是谁",
            "是什么",
            "是啥",
            "介绍一下",
            "介绍",
            "定义",
        ),
        "entity_attribute": (
            "长什么样",
            "长啥样",
            "是什么样",
            "是什么颜色",
            "是什么规格",
            "是什么",
            "是多少",
            "外貌是什么",
            "在哪里",
            "在哪",
            "外貌",
            "样子",
            "颜色",
            "重量",
            "尺寸",
            "规格",
            "配置",
            "属性",
            "特点",
            "特征",
            "办公地点",
            "地点",
            "位置",
            "的",
            "多少",
        ),
        "entity_reason": (
            "为什么受欢迎",
            "为什么这么火",
            "为什么火",
            "为什么",
            "受欢迎的原因",
            "受欢迎",
            "原因",
            "因素",
        ),
    }
    cleaned = question
    for pattern in cleanup_patterns.get(query_type, ()):
        cleaned = cleaned.replace(pattern, " ")
    term = _normalize_entity_term(cleaned)
    return (term,) if term else ()


def _normalize_entity_term(value: str) -> str:
    normalized = re.sub(r"[^\w\u3040-\u30ff\u4e00-\u9fffー]+", " ", value)
    normalized = " ".join(normalized.split()).strip()
    return normalized


def _has_entity_exact_match(text: str, *, profile: QueryEvidenceProfile) -> bool:
    if not profile.entity_terms:
        return False
    normalized_text = _normalize_text(text).lower()
    entity_hits = [
        term
        for term in profile.entity_terms
        if term and term.lower() in normalized_text
    ]
    if profile.query_type == "entity_relation":
        if len(entity_hits) >= min(2, len(profile.entity_terms)):
            return True
        return bool(entity_hits) and _intent_alignment(text, profile=profile) > 0
    return bool(entity_hits)


def _has_entity_context_match(
    *,
    unit_text: str,
    chunk: RetrievedChunk,
    metadata: object,
    lexical_relevance: float,
    intent_alignment: float,
    profile: QueryEvidenceProfile,
) -> bool:
    if profile.query_type not in ENTITY_CONTEXT_QUERY_TYPES:
        return False
    if not profile.entity_terms:
        return False
    if _has_entity_exact_match(unit_text, profile=profile):
        return False
    if intent_alignment <= 0:
        return False
    if lexical_relevance < ENTITY_CONTEXT_MIN_LEXICAL_RELEVANCE:
        return False

    structured_context_text = _build_structured_entity_context_text(
        chunk=chunk,
        metadata=metadata,
    )
    if _has_entity_exact_match(structured_context_text, profile=profile):
        return True

    return _has_local_entity_anchor(
        unit_text=unit_text,
        chunk=chunk,
        profile=profile,
    )


def _build_structured_entity_context_text(*, chunk: RetrievedChunk, metadata: object) -> str:
    section_title = getattr(metadata, "section_title", None) or chunk.section_title
    heading_path = getattr(metadata, "heading_path", None) or chunk.heading_path
    parts: list[str] = []
    if section_title:
        parts.append(str(section_title))
    if heading_path:
        parts.extend(str(item) for item in heading_path if item)
    return " ".join(parts)


def _build_bounded_unit_context_text(
    *,
    unit_text: str,
    chunk: RetrievedChunk,
    metadata: object,
) -> str:
    structured_context = _build_structured_entity_context_text(
        chunk=chunk,
        metadata=metadata,
    )
    return " ".join(part for part in (unit_text, structured_context) if part)


def _extract_technical_identifiers(question: str) -> tuple[str, ...]:
    identifiers = re.findall(
        r"`([^`]+)`|\b([A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+)\b|\b([a-z][a-z0-9]+_[a-z0-9_]+)\b",
        question,
    )
    flattened = [next((value for value in match if value), "") for match in identifiers]
    return tuple(dict.fromkeys(value for value in flattened if value))


def _technical_question_intent(question: str) -> str | None:
    lowered = question.casefold()
    if any(term in lowered for term in ("默认值", "default value", "default")):
        return "default_value"
    if any(term in lowered for term in ("支持哪些值", "哪些值", "supported values", "valid values")):
        return "supported_values"
    return None


def _technical_evidence_alignment(
    *,
    unit_text: str,
    structured_text: str,
    identifiers: tuple[str, ...],
    intent: str | None,
) -> float:
    if not identifiers:
        return 0.0
    context_tokens = set(_technical_identifier_tokens(structured_text))
    compact_context = "".join(_technical_identifier_tokens(structured_text))
    if not all(
        (
            set(_technical_identifier_tokens(identifier)).issubset(context_tokens)
            or "".join(_technical_identifier_tokens(identifier)) in compact_context
        )
        for identifier in identifiers
    ):
        return 0.0
    if intent == "default_value":
        lowered = unit_text.casefold()
        has_default_label = "default" in lowered or "默认" in lowered
        has_literal_value = bool(
            re.search(
                r"(?:^|[\s:=])(?:-?\d+(?:\.\d+)?|true|false|none|null)(?:$|[\s,.;，。])",
                lowered,
            )
        )
        return 1.0 if has_default_label and has_literal_value else 0.0
    if intent == "supported_values":
        lowered = unit_text.casefold()
        return 1.0 if any(
            term in lowered
            for term in (
                "supported values",
                "valid values",
                "supports",
                "options",
                "one of",
                "支持",
                "可选值",
            )
        ) else 0.0
    return 0.5


def _technical_identifier_tokens(value: str) -> list[str]:
    unquoted = re.sub(r"[`'\"]", " ", str(value or ""))
    split_camel = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", unquoted)
    raw_tokens = re.findall(r"[A-Za-z0-9]+", re.sub(r"[_-]+", " ", split_camel))
    return [_singularize_technical_token(token.casefold()) for token in raw_tokens if token]


def _singularize_technical_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _has_local_entity_anchor(
    *,
    unit_text: str,
    chunk: RetrievedChunk,
    profile: QueryEvidenceProfile,
) -> bool:
    if not chunk.text:
        return False

    unit_start = _find_unit_offset_in_chunk(unit_text=unit_text, chunk_text=chunk.text)
    if unit_start is None:
        return False

    local_context = _local_context_before_unit(
        chunk_text=chunk.text,
        unit_start=unit_start,
    )
    if not local_context:
        return False
    return _has_entity_exact_match(local_context, profile=profile)


def _find_unit_offset_in_chunk(*, unit_text: str, chunk_text: str) -> int | None:
    if not unit_text:
        return None
    direct_offset = chunk_text.find(unit_text)
    if direct_offset >= 0:
        return direct_offset

    normalized_unit = _normalize_text(unit_text)
    if not normalized_unit:
        return None
    direct_offset = chunk_text.find(normalized_unit)
    if direct_offset >= 0:
        return direct_offset

    prefix = normalized_unit[: min(24, len(normalized_unit))]
    if len(prefix) < 8:
        return None
    prefix_offset = chunk_text.find(prefix)
    return prefix_offset if prefix_offset >= 0 else None


SECTION_BOUNDARY_PATTERN = re.compile(
    r"(?m)^(?:#{1,6}\s+.+|[一二三四五六七八九十]+[、.．]\s*.+)$"
)


def _local_context_before_unit(*, chunk_text: str, unit_start: int) -> str:
    prefix = chunk_text[: max(0, unit_start)]
    boundary_start = 0
    for match in SECTION_BOUNDARY_PATTERN.finditer(prefix):
        boundary_start = match.start()
    local_context = prefix[boundary_start:]
    return _trim_text_for_prompt(local_context, max_chars=400)


def _intent_alignment(text: str, *, profile: QueryEvidenceProfile) -> float:
    if not profile.intent_terms:
        return 0.0
    normalized_text = _normalize_text(text).lower()
    hits = [
        term
        for term in profile.intent_terms
        if term and term.lower() in normalized_text
    ]
    return len(hits) / max(1, len(profile.intent_terms))


def build_citation_read_from_unit(item: CitationUnitCandidate) -> CitationRead:
    return CitationRead(
        citation_id=item.citation_id,
        citation_marker=item.marker,
        citation_unit_id=item.citation_unit_id,
        chunk_db_id=item.chunk_db_id,
        chunk_id=item.chunk_id,
        document_id=item.document_id,
        knowledge_base_id=item.knowledge_base_id,
        scope=item.scope,
        team_id=item.team_id,
        document_name=item.document_name,
        snippet=item.snippet,
        text=item.text,
        source_type=item.source_type,
        char_start=item.char_start,
        char_end=item.char_end,
        page_number=item.page_number,
        start_time=item.start_time,
        end_time=item.end_time,
        section_title=item.section_title,
        source_locator=build_source_locator_for_chunk(item),
        preview_target=build_preview_target_for_chunk(item),
        heading_path=list(item.heading_path) if item.heading_path else None,
    )


def build_citation_read_from_chunk(item: RetrievedChunk) -> CitationRead:
    return CitationRead(
        citation_marker=None,
        chunk_db_id=item.chunk_db_id,
        chunk_id=item.chunk_id,
        document_id=item.document_id,
        knowledge_base_id=item.knowledge_base_id,
        scope=item.scope,
        team_id=item.team_id,
        document_name=item.document_name,
        snippet=item.snippet,
        text=item.text,
        source_type=item.source_type,
        char_start=item.char_start,
        char_end=item.char_end,
        page_number=item.page_number,
        start_time=item.start_time,
        end_time=item.end_time,
        section_title=item.section_title,
        source_locator=build_source_locator_for_chunk(item),
        preview_target=build_preview_target_for_chunk(item),
        heading_path=list(item.heading_path) if item.heading_path else None,
    )


def resolve_answer_generator(settings: Settings | None = None) -> AnswerGenerator:
    active_settings = settings or get_settings()

    if active_settings.llm_provider == HEURISTIC_PROVIDER:
        return HeuristicAnswerGenerator()

    if active_settings.llm_provider == OPENAI_COMPATIBLE_PROVIDER:
        if not active_settings.llm_api_base:
            raise AnswerGenerationError(
                "LLM_API_BASE_URL is required for openai_compatible provider."
            )
        if not active_settings.llm_api_key:
            raise AnswerGenerationError("LLM_API_KEY is required for openai_compatible provider.")
        if not active_settings.llm_model:
            raise AnswerGenerationError("LLM_MODEL is required for openai_compatible provider.")

        return OpenAICompatibleAnswerGenerator(
            api_base=active_settings.llm_api_base,
            api_key=active_settings.llm_api_key,
            model=active_settings.llm_model,
            timeout_seconds=active_settings.llm_timeout_seconds,
        )

    if active_settings.llm_provider == DEEPSEEK_PROVIDER:
        if not active_settings.llm_api_base:
            raise AnswerGenerationError(
                "LLM_API_BASE_URL is required for deepseek provider."
            )
        if not active_settings.llm_api_key:
            raise AnswerGenerationError("LLM_API_KEY is required for deepseek provider.")
        if not active_settings.llm_model:
            raise AnswerGenerationError("LLM_MODEL is required for deepseek provider.")

        return OpenAICompatibleAnswerGenerator(
            api_base=active_settings.llm_api_base,
            api_key=active_settings.llm_api_key,
            model=active_settings.llm_model,
            timeout_seconds=active_settings.llm_timeout_seconds,
            reasoning_effort=active_settings.llm_reasoning_effort,
            thinking_enabled=active_settings.llm_thinking_enabled,
        )

    raise AnswerGenerationError(
        f"Unsupported LLM provider: {active_settings.llm_provider}."
    )


def build_fact_prompt(
    *,
    question: str,
    evidence_units: list[CitationUnitCandidate],
    conversation_context: Sequence[MessageContext] | None = None,
) -> PromptBundle:
    system_prompt = (
        "你是 PureLink 的知识库问答助手。"
        "以下最近对话上下文仅用于理解用户当前问题中的指代关系，不可作为事实依据。"
        "你只能根据给定的 evidence units 回答。"
        "每个事实性结论后必须标注来源编号，例如 [S1] 或 [S1][S2]。"
        f"如果证据不足，请直接回答：{NO_RELIABLE_EVIDENCE_MESSAGE}"
        "不要使用证据之外的知识。"
        "不要编造来源编号。"
        "不要引用未提供的编号。"
    )
    conversation_block = _build_conversation_context_block(conversation_context)
    context_block = _build_evidence_context_block(evidence_units)
    prompt_sections = [
        f"Question:\n{question}",
        f"Evidence Units:\n{context_block}",
    ]
    if conversation_block:
        prompt_sections.insert(0, f"Recent Conversation:\n{conversation_block}")
    user_prompt = "\n\n".join(prompt_sections)
    rendered_prompt = f"System:\n{system_prompt}\n\nUser:\n{user_prompt}"
    return PromptBundle(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        rendered_prompt=rendered_prompt,
    )


def build_overview_prompt(
    *,
    question: str,
    evidence_units: list[CitationUnitCandidate],
    conversation_context: Sequence[MessageContext] | None = None,
) -> PromptBundle:
    system_prompt = (
        "你是 PureLink 的知识库总结助手。"
        "以下最近对话上下文仅用于理解用户当前问题中的指代关系，不可作为事实依据。"
        "你只能根据提供的 evidence units 总结当前知识库。"
        "请用 3 到 6 个要点概括主要内容。"
        "每个要点后必须标注来源编号，例如 [S1] 或 [S1][S2]。"
        "如果资料不足，请明确说明当前知识库内容有限。"
        "不要使用 evidence units 之外的信息。"
        "不要编造来源编号。"
        "不要引用未提供的编号。"
    )
    conversation_block = _build_conversation_context_block(conversation_context)
    context_block = _build_evidence_context_block(evidence_units)
    prompt_sections = [
        f"Question:\n{question}",
        f"Evidence Units:\n{context_block}",
    ]
    if conversation_block:
        prompt_sections.insert(0, f"Recent Conversation:\n{conversation_block}")
    user_prompt = "\n\n".join(prompt_sections)
    rendered_prompt = f"System:\n{system_prompt}\n\nUser:\n{user_prompt}"
    return PromptBundle(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        rendered_prompt=rendered_prompt,
    )


def _build_evidence_context_block(evidence_units: list[CitationUnitCandidate]) -> str:
    context_lines: list[str] = []
    for unit in evidence_units:
        locator_parts = [f"document_name: {unit.document_name}"]
        if unit.source_type:
            locator_parts.append(f"source_type: {unit.source_type}")
        if unit.page_number is not None:
            locator_parts.append(f"page_number: {unit.page_number}")
        if unit.start_time is not None and unit.end_time is not None:
            locator_parts.append(
                f"time_range: {unit.start_time:.2f}-{unit.end_time:.2f}"
            )
        if unit.section_title:
            locator_parts.append(f"section_title: {unit.section_title}")
        if unit.source_locator:
            locator_parts.append(f"source_locator: {unit.source_locator}")
        context_lines.append(f"[{unit.marker}]")
        context_lines.extend(locator_parts)
        context_lines.append(f"content: {unit.text}")
        context_lines.append("")

    return "\n".join(context_lines).strip() if context_lines else "[no evidence]"


def _build_conversation_context_block(
    conversation_context: Sequence[MessageContext] | None,
) -> str:
    if not conversation_context:
        return ""

    lines: list[str] = []
    for item in conversation_context:
        lines.append(f"{item.role}: {item.content}")
    return "\n".join(lines)


def _compress_text(text: str, *, max_length: int = 260) -> str:
    normalized = _normalize_text(text)
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def _trim_text_for_prompt(text: str, *, max_chars: int) -> str:
    normalized = _normalize_text(text)
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _strip_citation_markers(text: str) -> str:
    return CITATION_MARKER_PATTERN.sub("", text)


def _is_redundant_chunk(candidate: RetrievedChunk, existing: list[RetrievedChunk]) -> bool:
    for previous in existing:
        if _shares_locator_context(candidate, previous):
            return True
        if _has_heavy_char_overlap(candidate, previous):
            return True
        if _has_heavy_text_overlap(candidate.text, previous.text):
            return True
    return False


def _has_heavy_char_overlap(left: RetrievedChunk, right: RetrievedChunk) -> bool:
    if (
        left.char_start is None
        or left.char_end is None
        or right.char_start is None
        or right.char_end is None
    ):
        return False

    left_start, left_end = sorted((left.char_start, left.char_end))
    right_start, right_end = sorted((right.char_start, right.char_end))
    overlap_start = max(left_start, right_start)
    overlap_end = min(left_end, right_end)
    if overlap_end <= overlap_start:
        return False

    overlap_width = overlap_end - overlap_start
    smaller_width = max(1, min(left_end - left_start, right_end - right_start))
    return (overlap_width / smaller_width) >= RANGE_OVERLAP_THRESHOLD


def _has_heavy_text_overlap(left_text: str, right_text: str) -> bool:
    left_tokens = set(tokenize_text(left_text))
    right_tokens = set(tokenize_text(right_text))
    if not left_tokens or not right_tokens:
        return False
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    if union == 0:
        return False
    return (intersection / union) >= TOKEN_JACCARD_THRESHOLD


def _normalize_text(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def _build_query_features(question: str) -> set[str]:
    normalized = _normalize_text(question).lower()
    features = _build_text_features(normalized)
    for phrase, synonyms in QUERY_SYNONYMS.items():
        if phrase not in normalized:
            continue
        features.add(phrase)
        for synonym in synonyms:
            features.update(_build_text_features(synonym))
    return features


def _build_text_features(text: str) -> set[str]:
    normalized = _normalize_text(text).lower()
    if not normalized:
        return set()

    features: set[str] = set()
    for token in tokenize_text(normalized):
        if CHINESE_CHARACTER_PATTERN.fullmatch(token):
            continue
        features.add(token)
    chinese_chars = CHINESE_CHARACTER_PATTERN.findall(normalized)
    compact_chinese = "".join(chinese_chars)
    for index in range(max(0, len(compact_chinese) - 1)):
        features.add(compact_chinese[index:index + 2])
    return {item for item in features if item}


def extract_used_citation_ids(answer_text: str) -> list[str]:
    used_markers: list[str] = []
    seen_markers: set[str] = set()
    for match in CITATION_MARKER_PATTERN.finditer(answer_text):
        for raw_token in match.group(1).split(","):
            normalized = _normalize_citation_marker(raw_token)
            if normalized is None or normalized in seen_markers:
                continue
            seen_markers.add(normalized)
            used_markers.append(normalized)
    return used_markers


def normalize_answer_citation_markers(
    *,
    answer_text: str,
    allowed_markers: set[str],
) -> str:
    def _replace(match: re.Match[str]) -> str:
        normalized_tokens: list[str] = []
        seen_tokens: set[str] = set()
        for raw_token in match.group(1).split(","):
            normalized = _normalize_citation_marker(raw_token)
            if normalized is None or normalized not in allowed_markers or normalized in seen_tokens:
                continue
            normalized_tokens.append(f"[{normalized}]")
            seen_tokens.add(normalized)
        return "".join(normalized_tokens)

    return CITATION_MARKER_PATTERN.sub(_replace, answer_text)


def _normalize_citation_marker(value: str) -> str | None:
    digits = re.sub(r"[^0-9]", "", value)
    if not digits:
        return None
    return f"S{int(digits)}"


def _shares_locator_context(left: RetrievedChunk, right: RetrievedChunk) -> bool:
    if left.source_locator and right.source_locator:
        return left.source_locator == right.source_locator
    if left.section_title and right.section_title:
        return left.section_title == right.section_title
    return False
