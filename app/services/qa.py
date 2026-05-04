from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
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
RANGE_OVERLAP_THRESHOLD = 0.6
TOKEN_JACCARD_THRESHOLD = 0.9
WHITESPACE_PATTERN = re.compile(r"\s+")


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
    citation_id: int
    citation_unit_id: int
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
    score: float


class AnswerGenerator(Protocol):
    def generate(
        self,
        *,
        question: str,
        retrieved_chunks: list[RetrievedChunk],
        prompt: PromptBundle,
    ) -> str: ...


class HeuristicAnswerGenerator:
    def generate(
        self,
        *,
        question: str,
        retrieved_chunks: list[RetrievedChunk],
        prompt: PromptBundle,
    ) -> str:
        if not retrieved_chunks:
            return NO_RELIABLE_EVIDENCE_MESSAGE

        snippets = [
            _compress_text(chunk.text)
            for chunk in retrieved_chunks[:2]
        ]
        return "Based on the knowledge base, the relevant information is: " + " ".join(snippets)


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
        retrieved_chunks: list[RetrievedChunk],
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
    prompt = build_prompt(question=question, retrieved_chunks=context_chunks)
    if not _has_reliable_retrieval_results(
        retrieved_chunks,
        min_score=active_settings.retrieval_min_score,
    ) or not context_chunks:
        answer = NO_RELIABLE_EVIDENCE_MESSAGE
        citations: list[CitationRead] = []
    else:
        answer_generator = generator or resolve_answer_generator(active_settings)
        answer = answer_generator.generate(
            question=question,
            retrieved_chunks=context_chunks,
            prompt=prompt,
        )
        citations = build_answer_citations(
            db=db,
            question=question,
            answer=answer,
            retrieved_chunks=context_chunks,
            max_citations=active_settings.max_citations,
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
    db: Session | None,
    question: str,
    answer: str,
    retrieved_chunks: list[RetrievedChunk],
    max_citations: int,
) -> list[CitationRead]:
    if db is None:
        return [build_citation_read_from_chunk(item) for item in organize_citations(retrieved_chunks, max_citations=max_citations)]
    chunk_units = load_citation_units_for_chunks(db=db, chunks=retrieved_chunks)
    selected_candidates = select_citation_candidates(
        question=question,
        answer=answer,
        retrieved_chunks=retrieved_chunks,
        chunk_units=chunk_units,
        max_citations=max_citations,
    )
    citations = [build_citation_read_from_unit(item) for item in selected_candidates]
    cited_chunk_ids = {item.chunk_id for item in selected_candidates}

    for chunk in organize_citations(retrieved_chunks, max_citations=max_citations):
        if len(citations) >= max_citations:
            break
        if chunk.chunk_id in cited_chunk_ids:
            continue
        citations.append(build_citation_read_from_chunk(chunk))

    return citations[:max_citations]


def load_citation_units_for_chunks(
    *,
    db: Session,
    chunks: list[RetrievedChunk],
) -> dict[str, list[DocumentCitationUnit]]:
    chunk_ids = [item.chunk_id for item in chunks]
    if not chunk_ids:
        return {}

    statement = (
        select(DocumentCitationUnit)
        .where(DocumentCitationUnit.chunk_key.in_(chunk_ids))
        .order_by(
            DocumentCitationUnit.document_id.asc(),
            DocumentCitationUnit.unit_index.asc(),
        )
    )
    units_by_chunk: dict[str, list[DocumentCitationUnit]] = defaultdict(list)
    for unit in db.scalars(statement):
        units_by_chunk[unit.chunk_key].append(unit)
    return units_by_chunk


def select_citation_candidates(
    *,
    question: str,
    answer: str,
    retrieved_chunks: list[RetrievedChunk],
    chunk_units: dict[str, list[DocumentCitationUnit]],
    max_citations: int,
) -> list[CitationUnitCandidate]:
    question_tokens = set(tokenize_text(question))
    answer_tokens = set(tokenize_text(answer))
    selected: list[CitationUnitCandidate] = []
    seen_keys: set[tuple[int, str, int]] = set()

    for chunk in retrieved_chunks:
        units = chunk_units.get(chunk.chunk_id)
        if not units:
            continue

        ranked_units = sorted(
            (
                _build_citation_unit_candidate(
                    unit=unit,
                    chunk=chunk,
                    question_tokens=question_tokens,
                    answer_tokens=answer_tokens,
                )
                for unit in units
            ),
            key=lambda item: (-item.score, item.document_id, item.chunk_id, item.citation_unit_id),
        )
        for candidate in ranked_units[:2]:
            candidate_key = (candidate.document_id, candidate.chunk_id, candidate.citation_unit_id)
            if candidate_key in seen_keys:
                continue
            selected.append(candidate)
            seen_keys.add(candidate_key)
            if len(selected) >= max_citations:
                return selected

    selected.sort(key=lambda item: (-item.score, item.document_id, item.chunk_id, item.citation_unit_id))
    return selected[:max_citations]


def _build_citation_unit_candidate(
    *,
    unit: DocumentCitationUnit,
    chunk: RetrievedChunk,
    question_tokens: set[str],
    answer_tokens: set[str],
) -> CitationUnitCandidate:
    metadata = parse_chunk_metadata(unit.metadata_json, fallback_source_type=chunk.source_type)
    question_overlap = _keyword_overlap(unit.unit_text, question_tokens)
    answer_overlap = _keyword_overlap(unit.unit_text, answer_tokens)
    score = (0.5 * chunk.score) + (0.3 * question_overlap) + (0.2 * answer_overlap)
    return CitationUnitCandidate(
        citation_id=unit.id,
        citation_unit_id=unit.id,
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
        score=score,
    )


def _keyword_overlap(text: str, reference_tokens: set[str]) -> float:
    if not reference_tokens:
        return 0.0
    tokens = set(tokenize_text(text))
    if not tokens:
        return 0.0
    return len(tokens & reference_tokens) / max(1, len(reference_tokens))


def build_citation_read_from_unit(item: CitationUnitCandidate) -> CitationRead:
    return CitationRead(
        citation_id=item.citation_id,
        citation_unit_id=item.citation_unit_id,
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
    retrieved_chunks: list[RetrievedChunk],
) -> PromptBundle:
    system_prompt = (
        "You are PureLink's knowledge base answerer. "
        "Answer only from the provided retrieval context. "
        "If the context is insufficient, say that no relevant information was found."
    )

    context_lines: list[str] = []
    for index, chunk in enumerate(retrieved_chunks, start=1):
        locator_parts = [f"document_name={chunk.document_name}"]
        if chunk.source_type:
            locator_parts.append(f"source_type={chunk.source_type}")
        if chunk.page_number is not None:
            locator_parts.append(f"page_number={chunk.page_number}")
        if chunk.start_time is not None and chunk.end_time is not None:
            locator_parts.append(
                f"time_range={chunk.start_time:.2f}-{chunk.end_time:.2f}"
            )
        if chunk.section_title:
            locator_parts.append(f"section_title={chunk.section_title}")
        if chunk.source_locator:
            locator_parts.append(f"source_locator={chunk.source_locator}")
        context_lines.append(
            f"[{index}] chunk_id={chunk.chunk_id} document_id={chunk.document_id} "
            f"knowledge_base_id={chunk.knowledge_base_id} score={chunk.score:.4f} "
            + " ".join(locator_parts)
        )
        context_lines.append(chunk.text)

    context_block = "\n".join(context_lines) if context_lines else "[no retrieval context]"
    user_prompt = f"Question:\n{question}\n\nContext:\n{context_block}"
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


def _shares_locator_context(left: RetrievedChunk, right: RetrievedChunk) -> bool:
    if left.source_locator and right.source_locator:
        return left.source_locator == right.source_locator
    if left.section_title and right.section_title:
        return left.section_title == right.section_title
    return False
