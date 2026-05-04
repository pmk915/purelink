from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging
import re
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.document_citation_unit import DocumentCitationUnit
from app.schemas.llm import (
    DEEPSEEK_PROVIDER,
    HEURISTIC_PROVIDER,
    OPENAI_COMPATIBLE_PROVIDER,
)
from app.schemas.qa import CitationRead
from app.services.chunk_metadata import build_chunk_snippet, parse_chunk_metadata
from app.services.document_embedding import RetrievedChunk, tokenize_text
from app.services.llm import LLMProviderError, generate_openai_compatible_chat_completion
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
    "怎么做": ("方法", "步骤", "流程"),
    "有什么用": ("作用", "用途", "功能"),
    "怎么保证": ("可靠性", "保证", "机制", "设计"),
}

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
    generator: AnswerGenerator | None = None,
    settings: Settings | None = None,
) -> QuestionAnswerResult:
    active_settings = settings or get_settings()
    context_chunks = select_context_chunks_for_answer(retrieved_chunks)
    chunk_units = load_citation_units_for_chunks(db=db, chunks=context_chunks) if db is not None else {}
    evidence_units = select_evidence_units(
        question=question,
        retrieved_chunks=context_chunks,
        chunk_units=chunk_units,
        max_evidence_units=max(MAX_ASK_EVIDENCE_UNITS, active_settings.max_citations),
    )
    logger.info(
        "qa evidence selected question=%s selected_chunk_ids=%s candidate_evidence_unit_count=%s fallback_chunk_citation_count=%s evidence_content_lengths=%s",
        question,
        [item.chunk_id for item in context_chunks],
        len(evidence_units),
        sum(1 for item in evidence_units if item.citation_unit_id is None),
        [len(item.text) for item in evidence_units],
    )
    prompt = build_prompt(question=question, evidence_units=evidence_units)
    if not _has_reliable_retrieval_results(
        context_chunks,
        min_score=active_settings.retrieval_min_score,
    ) or not evidence_units:
        answer = NO_RELIABLE_EVIDENCE_MESSAGE
        citations: list[CitationRead] = []
        logger.info(
            "qa answer skipped question=%s selected_chunk_ids=%s reason=%s",
            question,
            [item.chunk_id for item in context_chunks],
            "insufficient_retrieval_or_evidence",
        )
    else:
        answer_generator = generator or resolve_answer_generator(active_settings)
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
                "qa answer rejected question=%s used_marker_ids=%s reason=%s",
                question,
                used_markers,
                "no_valid_citation_markers",
            )
        else:
            citations = build_answer_citations(
                evidence_units=evidence_units,
                used_markers=used_markers,
                max_citations=active_settings.max_citations,
            )
            if not citations:
                answer = NO_RELIABLE_EVIDENCE_MESSAGE
            logger.info(
                "qa citations resolved question=%s used_marker_ids=%s used_citation_unit_ids=%s fallback_chunk_citation_count=%s returned_citation_count=%s",
                question,
                used_markers,
                [item.citation_unit_id for item in citations if item.citation_unit_id is not None],
                sum(1 for item in citations if item.citation_unit_id is None),
                len(citations),
            )
    return QuestionAnswerResult(
        answer=answer,
        citations=citations,
        prompt=prompt,
    )


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

    for chunk in retrieved_chunks:
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
) -> list[CitationUnitCandidate]:
    question_features = _build_query_features(question)
    selected: list[CitationUnitCandidate] = []
    seen_keys: set[tuple[int, str, int]] = set()

    for chunk in retrieved_chunks:
        units = chunk_units.get(chunk.chunk_id)
        ranked_units: list[CitationUnitCandidate]
        if units:
            ranked_units = sorted(
                (
                    _build_citation_unit_candidate(
                        unit=unit,
                        chunk=chunk,
                        question_features=question_features,
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
                )
            ]

        for candidate in ranked_units[:MAX_EVIDENCE_UNITS_PER_CHUNK]:
            candidate_key = (candidate.document_id, candidate.chunk_id, candidate.citation_unit_id or -1)
            if candidate_key in seen_keys:
                continue
            selected.append(candidate)
            seen_keys.add(candidate_key)
            if len(selected) >= max_evidence_units:
                break

    selected.sort(key=lambda item: (-item.score, item.document_id, item.chunk_id, item.citation_unit_id or -1))
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
        )
        for index, item in enumerate(selected[:max_evidence_units], start=1)
    ]


def _build_citation_unit_candidate(
    *,
    unit: DocumentCitationUnit,
    chunk: RetrievedChunk,
    question_features: set[str],
) -> CitationUnitCandidate:
    metadata = parse_chunk_metadata(unit.metadata_json, fallback_source_type=chunk.source_type)
    lexical_relevance = _lexical_relevance(unit.unit_text, question_features)
    score = (0.6 * chunk.score) + (0.4 * lexical_relevance)
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
    )


def _build_chunk_fallback_candidate(
    *,
    chunk: RetrievedChunk,
    question_features: set[str],
) -> CitationUnitCandidate:
    fallback_text = _resolve_chunk_fallback_text(chunk)
    lexical_relevance = _lexical_relevance(fallback_text, question_features)
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
        score=(0.6 * chunk.score) + (0.4 * lexical_relevance),
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


def _lexical_relevance(text: str, query_features: set[str]) -> float:
    if not query_features:
        return 0.0
    text_features = _build_text_features(text)
    if not text_features:
        return 0.0
    return len(text_features & query_features) / max(1, len(query_features))


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


def build_prompt(
    *,
    question: str,
    evidence_units: list[CitationUnitCandidate],
) -> PromptBundle:
    system_prompt = (
        "你是 PureLink 的知识库问答助手。"
        "你只能根据给定的 evidence units 回答。"
        "每个事实性结论后必须标注来源编号，例如 [S1] 或 [S1][S2]。"
        f"如果证据不足，请直接回答：{NO_RELIABLE_EVIDENCE_MESSAGE}"
        "不要使用证据之外的知识。"
        "不要编造来源编号。"
        "不要引用未提供的编号。"
    )

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
        context_lines.append(
            f"[{unit.marker}]"
        )
        context_lines.extend(locator_parts)
        context_lines.append(f"content: {unit.text}")
        context_lines.append("")

    context_block = "\n".join(context_lines).strip() if context_lines else "[no evidence]"
    user_prompt = f"Question:\n{question}\n\nEvidence Units:\n{context_block}"
    rendered_prompt = f"System:\n{system_prompt}\n\nUser:\n{user_prompt}"
    return PromptBundle(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        rendered_prompt=rendered_prompt,
    )


def _compress_text(text: str, *, max_length: int = 260) -> str:
    normalized = _normalize_text(text)
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


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
