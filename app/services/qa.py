from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
from typing import Protocol

from app.core.config import Settings, get_settings
from app.schemas.llm import HEURISTIC_PROVIDER, OPENAI_COMPATIBLE_PROVIDER
from app.schemas.qa import CitationRead
from app.services.document_embedding import RetrievedChunk, tokenize_text
from app.services.llm import LLMProviderError, generate_openai_compatible_chat_completion
from app.services.source_locator import (
    build_preview_target_for_chunk,
    build_source_locator_for_chunk,
)


NO_ANSWER_FOUND_MESSAGE = "I could not find relevant information in the knowledge base."
MAX_ASK_CONTEXT_CHUNKS = 6
MAX_ASK_CONTEXT_TOTAL_CHARS = 4200
MAX_ASK_CHUNKS_PER_DOCUMENT = 2
MAX_ASK_CITATIONS = 6
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
            return NO_ANSWER_FOUND_MESSAGE

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
    ) -> None:
        self.api_base = api_base
        self.api_key = api_key
        self.model = model

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
            )
        except LLMProviderError as exc:
            raise AnswerGenerationError(str(exc)) from exc


def answer_question(
    *,
    question: str,
    retrieved_chunks: list[RetrievedChunk],
    generator: AnswerGenerator | None = None,
) -> QuestionAnswerResult:
    context_chunks = select_context_chunks_for_answer(retrieved_chunks)
    prompt = build_prompt(question=question, retrieved_chunks=context_chunks)
    if not context_chunks:
        answer = NO_ANSWER_FOUND_MESSAGE
    else:
        answer_generator = generator or resolve_answer_generator()
        answer = answer_generator.generate(
            question=question,
            retrieved_chunks=context_chunks,
            prompt=prompt,
        )
    citations = [
        CitationRead(
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
        for item in organize_citations(context_chunks)
    ]
    return QuestionAnswerResult(
        answer=answer,
        citations=citations,
        prompt=prompt,
    )


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
    max_citations: int = MAX_ASK_CITATIONS,
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


def resolve_answer_generator(settings: Settings | None = None) -> AnswerGenerator:
    active_settings = settings or get_settings()

    if active_settings.llm_provider == HEURISTIC_PROVIDER:
        return HeuristicAnswerGenerator()

    if active_settings.llm_provider == OPENAI_COMPATIBLE_PROVIDER:
        if not active_settings.llm_api_base:
            raise AnswerGenerationError("LLM_API_BASE is required for openai_compatible provider.")
        if not active_settings.llm_api_key:
            raise AnswerGenerationError("LLM_API_KEY is required for openai_compatible provider.")
        if not active_settings.llm_model:
            raise AnswerGenerationError("LLM_MODEL is required for openai_compatible provider.")

        return OpenAICompatibleAnswerGenerator(
            api_base=active_settings.llm_api_base,
            api_key=active_settings.llm_api_key,
            model=active_settings.llm_model,
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
