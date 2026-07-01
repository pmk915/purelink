from __future__ import annotations

import json

from app.services.retrieval.types import RetrievedEvidence, RetrievalMode, RetrievalResult
from scripts.eval.rag_eval import RagEvalCase, evaluate_retrieval_result
from scripts.eval.rag_eval_baseline import (
    REQUIRED_SUMMARY_SECTIONS,
    baseline_summary_to_dict,
    default_baselines,
    load_baseline_cases,
    render_summary_markdown,
    source_paths_for_cases,
    summarize_baseline_results,
    validate_summary_markdown,
)


def test_baseline_case_schema_loads_json_array(tmp_path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "case_001",
                    "question": "CHUNK_STRATEGY 在哪里配置？",
                    "expected_answer_contains": ["CHUNK_STRATEGY", "block_aware"],
                    "expected_source_hint": "docs/ingestion/document-blocks.md",
                    "case_type": "technical",
                    "expected_mode": "hybrid_text",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cases = load_baseline_cases(path)

    assert len(cases) == 1
    assert cases[0].id == "case_001"
    assert cases[0].expected_answer_contains == ("CHUNK_STRATEGY", "block_aware")
    assert source_paths_for_cases(cases) == ("docs/ingestion/document-blocks.md",)


def test_default_baseline_config_generates_required_comparison_set() -> None:
    baselines = default_baselines()

    assert [item.name for item in baselines] == [
        "fixed_chunk_only",
        "block_aware_chunk_only",
        "block_aware_hybrid_text",
        "block_aware_graph_vector_mix",
        "block_aware_auto",
    ]
    assert baselines[0].chunk_strategy == "fixed"
    assert baselines[-1].mode == "auto"


def test_metric_calculation_records_selected_mode_and_router_reason() -> None:
    case = RagEvalCase(
        id="case-auto",
        question="/api/kb/documents 接口在哪里？",
        knowledge_base_id=1,
        mode="auto",
        expected_doc_names=("docs/rag/retrieval-layer.md",),
        expected_keywords=("HYBRID_TEXT", "API paths"),
    )
    result = RetrievalResult(
        query=case.question,
        mode=RetrievalMode.HYBRID_TEXT,
        requested_mode=RetrievalMode.AUTO,
        selected_mode=RetrievalMode.HYBRID_TEXT,
        router_reason="question contains API/path/config/code-like tokens",
        evidences=[
            RetrievedEvidence(
                document_id=1,
                chunk_id="1:0",
                citation_unit_id=10,
                document_name="docs/rag/retrieval-layer.md",
                text="HYBRID_TEXT helps API paths.",
            )
        ],
        context_text="HYBRID_TEXT helps API paths.",
        trace_id=123,
    )

    evaluated = evaluate_retrieval_result(case, result, latency_ms=17)

    assert evaluated.retrieval_hit is True
    assert evaluated.citation_hit is True
    assert evaluated.keyword_coverage == 1.0
    assert evaluated.requested_mode == "auto"
    assert evaluated.selected_mode == "hybrid_text"
    assert evaluated.router_reason == "question contains API/path/config/code-like tokens"
    assert evaluated.latency_ms == 17


def test_summary_markdown_contains_required_sections() -> None:
    case = RagEvalCase(
        id="case-1",
        question="q",
        knowledge_base_id=1,
        expected_doc_names=("doc.md",),
        expected_keywords=("keyword",),
    )
    evaluated = evaluate_retrieval_result(
        case,
        RetrievalResult(
            query="q",
            mode=RetrievalMode.CHUNK_ONLY,
            evidences=[
                RetrievedEvidence(
                    document_id=1,
                    chunk_id="1:0",
                    citation_unit_id=1,
                    document_name="doc.md",
                    text="keyword",
                )
            ],
            context_text="keyword",
            trace_id=1,
        ),
        latency_ms=5,
    )
    summary = summarize_baseline_results([evaluated])
    baselines = [
        baseline_summary_to_dict(
            baseline=baseline,
            summary=summary,
        )
        for baseline in default_baselines()
    ]
    markdown = render_summary_markdown(
        {
            "cases_path": "docs/interview/rag-eval-cases.json",
            "case_count": 1,
            "case_type_counts": {"technical": 1},
            "data_sources": ["doc.md"],
            "baselines": baselines,
        }
    )

    validate_summary_markdown(markdown)
    for section in REQUIRED_SUMMARY_SECTIONS:
        assert section in markdown
