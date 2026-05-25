from __future__ import annotations

from app.services.retrieval.types import RetrievedEvidence, RetrievalMode, RetrievalResult
from scripts.eval.rag_eval import (
    RagEvalCase,
    calculate_citation_hit,
    calculate_keyword_coverage,
    calculate_retrieval_hit,
    evaluate_retrieval_result,
    parse_case,
    summarize_results,
)


def test_retrieval_hit_true_when_expected_doc_appears() -> None:
    evidences = [
        _evidence(document_id=1, document_name="team-permissions.md"),
    ]

    assert calculate_retrieval_hit(
        evidences,
        expected_doc_names=("team-permissions.md",),
    )


def test_retrieval_hit_false_when_expected_doc_missing() -> None:
    evidences = [
        _evidence(document_id=1, document_name="other.md"),
    ]

    assert not calculate_retrieval_hit(
        evidences,
        expected_doc_names=("team-permissions.md",),
    )


def test_retrieval_hit_can_fallback_to_document_id() -> None:
    evidences = [
        _evidence(document_id=42, document_name=None),
    ]

    assert calculate_retrieval_hit(
        evidences,
        expected_doc_names=(),
        expected_doc_ids=(42,),
    )


def test_citation_hit_requires_citation_unit_when_required() -> None:
    evidences = [
        _evidence(document_id=1, document_name="team-permissions.md", citation_unit_id=None),
        _evidence(document_id=2, document_name="other.md", citation_unit_id=20),
    ]

    assert not calculate_citation_hit(
        evidences,
        expected_doc_names=("team-permissions.md",),
        expected_citation_required=True,
    )


def test_citation_hit_passes_when_not_required() -> None:
    assert calculate_citation_hit(
        [],
        expected_doc_names=("team-permissions.md",),
        expected_citation_required=False,
    )


def test_keyword_coverage_tracks_matched_and_missing_keywords() -> None:
    result = calculate_keyword_coverage(
        text="管理员可以删除团队文件。PureLink keeps citations.",
        expected_keywords=("管理员", "删除", "missing", "CITATIONS"),
    )

    assert result.coverage == 0.75
    assert result.matched_keywords == ("管理员", "删除", "CITATIONS")
    assert result.missing_keywords == ("missing",)


def test_empty_expected_keywords_returns_full_coverage() -> None:
    result = calculate_keyword_coverage(text="", expected_keywords=())

    assert result.coverage == 1.0
    assert result.matched_keywords == ()
    assert result.missing_keywords == ()


def test_evaluate_retrieval_result_records_trace_and_reranker_metrics() -> None:
    case = RagEvalCase(
        id="case-1",
        question="Who can delete team files?",
        knowledge_base_id=1,
        expected_doc_names=("team-permissions.md",),
        expected_keywords=("管理员", "删除"),
        expected_citation_required=True,
    )
    result = RetrievalResult(
        query=case.question,
        mode=RetrievalMode.CHUNK_ONLY,
        evidences=[
            _evidence(
                document_id=1,
                document_name="team-permissions.md",
                citation_unit_id=10,
                text="管理员可以删除团队文件。",
            )
        ],
        context_text="[S1] 管理员可以删除团队文件。",
        used_reranker=True,
        trace_id=123,
    )

    evaluated = evaluate_retrieval_result(
        case,
        result,
        trace_item_count=2,
        initial_candidate_count=5,
    )

    assert evaluated.retrieval_hit is True
    assert evaluated.citation_hit is True
    assert evaluated.keyword_coverage == 1.0
    assert evaluated.used_reranker is True
    assert evaluated.trace_available is True
    assert evaluated.trace_id == 123
    assert evaluated.top_documents == ("team-permissions.md",)
    assert evaluated.trace_item_count == 2
    assert evaluated.initial_candidate_count == 5


def test_summarize_results_calculates_rates() -> None:
    case = RagEvalCase(
        id="case-1",
        question="q",
        knowledge_base_id=1,
        expected_doc_names=("doc.md",),
    )
    passed = evaluate_retrieval_result(
        case,
        RetrievalResult(
            query="q",
            mode=RetrievalMode.CHUNK_ONLY,
            evidences=[_evidence(document_id=1, document_name="doc.md", citation_unit_id=1)],
            context_text="",
            trace_id=1,
        ),
    )
    failed = evaluate_retrieval_result(
        case,
        RetrievalResult(
            query="q",
            mode=RetrievalMode.CHUNK_ONLY,
            evidences=[],
            context_text="",
            trace_id=None,
        ),
    )

    summary = summarize_results([passed, failed])

    assert summary.total_cases == 2
    assert summary.retrieval_hit_rate == 0.5
    assert summary.citation_hit_rate == 0.5
    assert summary.trace_available_count == 1


def test_parse_case_accepts_graph_vector_mix_mode() -> None:
    case = parse_case(
        {
            "id": "graph-case",
            "question": "谁可以删除文档？",
            "knowledge_base_id": 1,
            "mode": "graph_vector_mix",
        }
    )

    assert case.mode == RetrievalMode.GRAPH_VECTOR_MIX.value


def test_parse_case_accepts_hybrid_text_mode() -> None:
    case = parse_case(
        {
            "id": "hybrid-case",
            "question": "/api/v1/knowledge-bases/{id}/rag-health 返回什么？",
            "knowledge_base_id": 1,
            "mode": "hybrid_text",
        }
    )

    assert case.mode == RetrievalMode.HYBRID_TEXT.value


def _evidence(
    *,
    document_id: int,
    document_name: str | None,
    citation_unit_id: int | None = 1,
    text: str = "evidence text",
) -> RetrievedEvidence:
    return RetrievedEvidence(
        document_id=document_id,
        chunk_id="chunk-1",
        citation_unit_id=citation_unit_id,
        text=text,
        document_name=document_name,
    )
