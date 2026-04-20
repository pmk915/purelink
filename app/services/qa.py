from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings, get_settings
from app.schemas.llm import HEURISTIC_PROVIDER, OPENAI_COMPATIBLE_PROVIDER
from app.schemas.qa import CitationRead
from app.services.document_embedding import RetrievedChunk
from app.services.llm import LLMProviderError, generate_openai_compatible_chat_completion


NO_ANSWER_FOUND_MESSAGE = "I could not find relevant information in the indexed knowledge base."


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
        return "Based on the indexed knowledge base, the relevant information is: " + " ".join(snippets)


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
    prompt = build_prompt(question=question, retrieved_chunks=retrieved_chunks)
    if not retrieved_chunks:
        answer = NO_ANSWER_FOUND_MESSAGE
    else:
        answer_generator = generator or resolve_answer_generator()
        answer = answer_generator.generate(
            question=question,
            retrieved_chunks=retrieved_chunks,
            prompt=prompt,
        )
    citations = [
        CitationRead(
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            knowledge_base_id=item.knowledge_base_id,
            scope=item.scope,
            team_id=item.team_id,
            text=item.text,
        )
        for item in retrieved_chunks
    ]
    return QuestionAnswerResult(
        answer=answer,
        citations=citations,
        prompt=prompt,
    )


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
        context_lines.append(
            f"[{index}] chunk_id={chunk.chunk_id} document_id={chunk.document_id} "
            f"knowledge_base_id={chunk.knowledge_base_id} score={chunk.score:.4f}"
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
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."
