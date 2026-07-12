from __future__ import annotations

import pytest

from app.services.evidence_support import (
    REASON_MISSING_ATTRIBUTE_SUPPORT,
    REASON_SUPPORTED,
    evaluate_evidence_support,
)
from app.services.qa import NO_RELIABLE_EVIDENCE_MESSAGE, answer_question, build_query_evidence_profile
from app.services.retrieval.types import RetrievedEvidence


class CountingAnswerGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *, question, evidence_units, prompt) -> str:  # noqa: ANN001
        self.calls += 1
        return "不应该调用 provider [S1]。"


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


def _decision(question: str, text: str, *, score: float = 0.88):
    return evaluate_evidence_support(
        query=question,
        evidence_units=[_evidence(text=text, score=score)],
        profile=build_query_evidence_profile(question),
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


def _chunk(*, text: str, score: float):
    from app.models.enums import KnowledgeBaseScope
    from app.services.document_embedding import RetrievedChunk

    return RetrievedChunk(
        chunk_id="1:0",
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
        section_title=None,
        source_locator=None,
        heading_path=None,
        score=score,
        chunk_db_id=1,
    )
