from __future__ import annotations

import pytest

from app.services.evidence_support import (
    REASON_MISSING_ATTRIBUTE_SUPPORT,
    REASON_SUPPORTED,
    evaluate_evidence_support,
)
from app.services.qa import (
    NO_RELIABLE_EVIDENCE_MESSAGE,
    CitationUnitCandidate,
    answer_question,
    build_query_evidence_profile,
)
from app.services.retrieval.citation_builder import build_evidences
from app.services.retrieval.types import RetrievedEvidence, RetrievalMode, RetrievalResult


class CountingAnswerGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *, question, evidence_units, prompt) -> str:  # noqa: ANN001
        self.calls += 1
        return "不应该调用 provider [S1]。"


class CapturingAnswerGenerator:
    def __init__(self) -> None:
        self.evidence_texts: list[str] = []

    def generate(self, *, question, evidence_units, prompt) -> str:  # noqa: ANN001
        self.evidence_texts = [item.text for item in evidence_units]
        return f"基于支持证据回答 [{evidence_units[0].marker}]。"


def test_support_gate_rejects_unsupported_answer_and_skips_provider() -> None:
    generator = CountingAnswerGenerator()

    result = answer_question(
        question="Alice Chen 在哪里办公？",
        retrieved_chunks=[
            _chunk(
                text="Alice Chen 负责向量索引、混合检索和 reranker 评测。",
                score=0.92,
            )
        ],
        generator=generator,
    )

    assert result.answer == NO_RELIABLE_EVIDENCE_MESSAGE
    assert result.citations == []
    assert result.evidence_support is not None
    assert result.evidence_support.reason == REASON_MISSING_ATTRIBUTE_SUPPORT
    assert generator.calls == 0


def test_support_gate_accepts_supported_attribute_question() -> None:
    decision = _decision(
        "Alice Chen 在哪里办公？",
        "Alice Chen 的角色是检索工程师，办公地点：Singapore，负责向量索引、混合检索和 reranker 评测。",
        score=0.91,
    )

    assert decision.answerable is True
    assert decision.reason == REASON_SUPPORTED
    assert decision.signals["requested_attribute_coverage"] is True


def test_support_gate_rejects_wrong_attribute_even_with_entity_and_high_score() -> None:
    decision = _decision(
        "Alice Chen 的生日是什么？",
        "Alice Chen 的办公地点是 Singapore，负责向量索引和混合检索。",
        score=0.96,
    )

    assert decision.answerable is False
    assert decision.reason == REASON_MISSING_ATTRIBUTE_SUPPORT
    assert decision.signals["entity_coverage"] is True
    assert decision.signals["retrieval_score_support"] is True


def test_support_gate_accepts_supported_reason_question() -> None:
    decision = _decision(
        "PostgreSQL 为什么使用 MVCC？",
        "PostgreSQL uses multiversion concurrency control, or MVCC, so readers and writers can often operate without blocking each other and preserve consistency.",
    )

    assert decision.answerable is True
    assert decision.signals["requested_intent_coverage"] is True


def test_support_gate_accepts_supported_relation_question() -> None:
    decision = _decision(
        "Alice Chen 和 Bob Li 是什么关系？",
        "Alice Chen 的合作伙伴是 Bob Li。Bob Li 与 Alice Chen 协作维护评测运行环境。",
    )

    assert decision.answerable is True
    assert decision.signals["relation_entity_coverage"] is True


def test_support_gate_accepts_supported_exact_identifier_question() -> None:
    decision = _decision(
        "docker compose down -v 会删除什么？",
        "`docker compose down -v` removes volumes, so local database and Redis data stored in volumes are deleted.",
    )

    assert decision.answerable is True
    assert decision.signals["exact_identifier_coverage"] is True


@pytest.mark.parametrize(
    "identifier_variant",
    [
        "CHUNK_STRATEGY",
        "chunk_strategy",
        "chunk-strategy",
        "chunk strategy",
        "Chunk Strategies",
    ],
)
def test_exact_technical_identifier_variants_support_value_question(identifier_variant: str) -> None:
    decision = evaluate_evidence_support(
        query="CHUNK_STRATEGY 支持哪些值？",
        evidence_units=[
            _evidence(
                text="PureLink supports fixed and block_aware chunk strategies.",
                section_title=identifier_variant,
            )
        ],
        profile=build_query_evidence_profile("CHUNK_STRATEGY 支持哪些值？"),
    )

    assert decision.answerable is True
    assert decision.reason == REASON_SUPPORTED
    assert decision.signals["exact_identifier_coverage"] is True


def test_exact_technical_identifier_in_heading_combines_with_fact_in_same_document() -> None:
    question = "CHUNK_STRATEGY 支持哪些值？"
    decision = evaluate_evidence_support(
        query=question,
        evidence_units=[
            _evidence(text="Configuration reference", heading_path=["Chunk Strategies"], chunk_id="1:0"),
            _evidence(text="Supported values are fixed and block_aware.", chunk_id="1:1"),
        ],
        profile=build_query_evidence_profile(question),
    )

    assert decision.answerable is True


def test_exact_technical_default_requires_the_requested_value() -> None:
    decision = _decision(
        "RETRIEVAL_MIN_SCORE 默认值是什么？",
        "RETRIEVAL_MIN_SCORE controls minimum-score filtering.",
    )

    assert decision.answerable is False


def test_exact_technical_rejects_mismatched_attribute_intent() -> None:
    decision = _decision(
        "CHUNK_STRATEGY 的作者是谁？",
        "CHUNK_STRATEGY supports fixed and block_aware values.",
    )

    assert decision.answerable is False


def test_exact_technical_rejects_adjacent_content_without_identifier() -> None:
    decision = _decision(
        "CHUNK_STRATEGY 支持哪些值？",
        "The parser supports fixed-width tables and block-aware PDF extraction.",
    )

    assert decision.answerable is False


@pytest.mark.parametrize(
    ("question", "evidence", "expected_reason"),
    [
        (
            "Acme 去年利润是多少？",
            "Acme 员工政策说明了假期、远程办公和绩效沟通规则。",
            REASON_MISSING_ATTRIBUTE_SUPPORT,
        ),
        (
            "Acme 的 CEO 是谁？",
            "Acme 员工政策说明了团队成员的办公地点和职责。",
            REASON_MISSING_ATTRIBUTE_SUPPORT,
        ),
        (
            "Acme 什么时候上市？",
            "Acme 员工政策说明了远程办公审批流程和员工福利。",
            REASON_MISSING_ATTRIBUTE_SUPPORT,
        ),
        (
            "Aurora Mini 的处理器型号是什么？",
            "Aurora Mini 的颜色是银色，重量是 1.2 kg，特点是便携。",
            REASON_MISSING_ATTRIBUTE_SUPPORT,
        ),
        (
            "Alice Chen 的生日是什么？",
            "Alice Chen 的办公地点是 Singapore，负责向量索引和混合检索。",
            REASON_MISSING_ATTRIBUTE_SUPPORT,
        ),
    ],
)
def test_focused_no_answer_cases_reject_non_supporting_evidence(
    question: str,
    evidence: str,
    expected_reason: str,
) -> None:
    decision = _decision(question, evidence, score=0.97)

    assert decision.answerable is False
    assert decision.reason == expected_reason
    assert decision.signals["has_final_evidence"] is True
    assert decision.signals["retrieval_score_support"] is True


@pytest.mark.parametrize(
    ("question", "evidence"),
    [
        ("Alice Chen 负责什么？", "Alice Chen 负责：向量索引、混合检索和 reranker 评测。"),
        ("Aurora Mini 是什么颜色？", "Aurora Mini 的颜色：银色，重量：1.2 kg。"),
        ("Aurora Mini 重量是多少？", "Aurora Mini 的颜色：银色，重量：1.2 kg。"),
        ("Employee policy 的远程办公规则是什么？", "Employee policy says remote work requires manager approval and weekly status updates."),
        ("RETRIEVAL_MIN_SCORE 默认值是什么？", "`RETRIEVAL_MIN_SCORE` has a default value of 0.0."),
        ("Python 类是什么？", "A Python class is a user-defined type that organizes data and behavior together."),
        ("PostgreSQL 为什么使用 MVCC？", "PostgreSQL uses MVCC so readers and writers can often operate without blocking each other."),
        ("Alice Chen 和 Bob Li 是什么关系？", "Alice Chen 的合作伙伴是 Bob Li。"),
        ("总结 PureLink retrieval 文档。", "PureLink retrieval includes Retrieval Modes, Evidence Selection, traces, and citations."),
    ],
)
def test_positive_paired_cases_remain_supported(question: str, evidence: str) -> None:
    decision = _decision(question, evidence)

    assert decision.answerable is True
    assert decision.reason == REASON_SUPPORTED


def test_attribute_provider_receives_only_entity_attribute_support() -> None:
    generator = CapturingAnswerGenerator()
    candidates = [
        _candidate(1, "Alice Chen 的办公地点是 Singapore。", "Alice Chen"),
        _candidate(2, "Bob Li 的办公地点是 Shanghai。", "Bob Li"),
        _candidate(3, "Carol Wang 的办公地点是 Beijing。", "Carol Wang"),
    ]

    result, retrieval_result = _answer_from_candidates(
        question="Alice Chen 在哪里办公？",
        candidates=candidates,
        generator=generator,
    )

    assert result.answer_policy is not None
    assert result.answer_policy.allow_provider_call is True
    assert generator.evidence_texts == ["Alice Chen 的办公地点是 Singapore。"]
    assert [item.text for item in retrieval_result.evidences] == generator.evidence_texts
    assert retrieval_result.metadata["support_aware_narrowing_applied"] is True


def test_exact_technical_provider_excludes_adjacent_config_keys() -> None:
    generator = CapturingAnswerGenerator()
    candidates = [
        _candidate(
            1,
            "CHUNK_STRATEGY supports the values fixed and block_aware.",
            "CHUNK_STRATEGY",
        ),
        _candidate(
            2,
            "EMBEDDING_PROVIDER supports fastembed and local_hashed_bow.",
            "EMBEDDING_PROVIDER",
        ),
    ]

    _, retrieval_result = _answer_from_candidates(
        question="CHUNK_STRATEGY 支持哪些值？",
        candidates=candidates,
        generator=generator,
    )

    assert generator.evidence_texts == [
        "CHUNK_STRATEGY supports the values fixed and block_aware."
    ]
    assert [item.text for item in retrieval_result.evidences] == generator.evidence_texts


def test_relation_provider_requires_the_explicit_entity_relation() -> None:
    generator = CapturingAnswerGenerator()
    candidates = [
        _candidate(1, "Alice Chen 的合作伙伴是 Bob Li。", "Relationships"),
        _candidate(2, "Alice Chen 在 Singapore 办公。", "Alice Chen"),
        _candidate(3, "Bob Li 在 Shanghai 办公。", "Bob Li"),
    ]

    _, retrieval_result = _answer_from_candidates(
        question="Alice Chen 和 Bob Li 是什么关系？",
        candidates=candidates,
        generator=generator,
    )

    assert generator.evidence_texts == ["Alice Chen 的合作伙伴是 Bob Li。"]
    assert [item.text for item in retrieval_result.evidences] == generator.evidence_texts


def test_overview_provider_preserves_evidence_breadth() -> None:
    generator = CapturingAnswerGenerator()
    candidates = [
        _candidate(1, "Structured ingestion preserves document blocks.", "Ingestion"),
        _candidate(2, "Routed retrieval exposes the selected mode.", "Retrieval"),
        _candidate(3, "Answer Policy blocks unsupported generation.", "Answers"),
    ]

    _, retrieval_result = _answer_from_candidates(
        question="总结 PureLink 的主要能力。",
        candidates=candidates,
        generator=generator,
        mode=RetrievalMode.OVERVIEW,
    )

    assert generator.evidence_texts == [item.text for item in candidates]
    assert [item.text for item in retrieval_result.evidences] == generator.evidence_texts
    assert retrieval_result.metadata["support_aware_narrowing_applied"] is False


def _decision(question: str, text: str, *, score: float = 0.88):
    return evaluate_evidence_support(
        query=question,
        evidence_units=[_evidence(text=text, score=score)],
        profile=build_query_evidence_profile(question),
    )


def _answer_from_candidates(
    *,
    question: str,
    candidates: list[CitationUnitCandidate],
    generator: CapturingAnswerGenerator,
    mode: RetrievalMode = RetrievalMode.CHUNK_ONLY,
):
    chunks = [
        _chunk(
            text=item.text,
            score=item.score,
            chunk_id=item.chunk_id,
            section_title=item.section_title,
        )
        for item in candidates
    ]
    retrieval_result = RetrievalResult(
        query=question,
        mode=mode,
        requested_mode=RetrievalMode.AUTO,
        selected_mode=mode,
        effective_mode=mode,
        evidences=build_evidences(candidates),
        context_text="\n".join(item.text for item in candidates),
        metadata={
            "retrieved_chunks": chunks,
            "context_chunks": chunks,
            "evidence_units": candidates,
        },
    )
    result = answer_question(
        question=question,
        retrieved_chunks=chunks,
        retrieval_result=retrieval_result,
        generator=generator,
    )
    return result, retrieval_result


def _candidate(
    index: int,
    text: str,
    section_title: str,
) -> CitationUnitCandidate:
    return CitationUnitCandidate(
        marker=f"S{index}",
        citation_id=index,
        citation_unit_id=index,
        chunk_db_id=index,
        chunk_id=f"1:{index}",
        document_id=1,
        knowledge_base_id=1,
        scope="personal",
        team_id=None,
        document_name="support.txt",
        text=text,
        snippet=text,
        source_type="text",
        char_start=index * 100,
        char_end=index * 100 + len(text),
        page_number=None,
        start_time=None,
        end_time=None,
        section_title=section_title,
        source_locator=f"section:{section_title}",
        heading_path=(section_title,),
        lexical_relevance=0.9,
        score=0.9,
    )


def _evidence(
    *,
    text: str,
    score: float = 0.88,
    document_id: int = 1,
    chunk_id: str = "1:0",
    section_title: str | None = None,
    heading_path: list[str] | None = None,
) -> RetrievedEvidence:
    return RetrievedEvidence(
        document_id=document_id,
        chunk_id=chunk_id,
        chunk_db_id=1,
        text=text,
        document_name="support.txt",
        final_score=score,
        section_title=section_title,
        heading_path=heading_path,
        metadata={"marker": "S1"},
    )


def _chunk(
    *,
    text: str,
    score: float,
    chunk_id: str = "1:0",
    section_title: str | None = None,
):
    from app.models.enums import KnowledgeBaseScope
    from app.services.document_embedding import RetrievedChunk

    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        knowledge_base_id=1,
        scope=KnowledgeBaseScope.PERSONAL.value,
        team_id=None,
        document_name="support.txt",
        text=text,
        snippet=text,
        source_type="text",
        char_start=None,
        char_end=None,
        page_number=None,
        start_time=None,
        end_time=None,
        section_title=section_title,
        source_locator=f"section:{section_title}" if section_title else None,
        heading_path=(section_title,) if section_title else None,
        score=score,
        chunk_db_id=1,
    )
