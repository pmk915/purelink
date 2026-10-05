from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import json
from types import SimpleNamespace

import pytest

from app.services.retrieval.types import RetrievedEvidence, RetrievalMode, RetrievalResult
from scripts.eval.rag_eval import (
    RagEvalCase, calculate_document_recall, calculate_document_mrr, calculate_evidence_recall,
    evaluate_retrieval_result, failed_case_result, parse_case, ranked_document_snapshot,
    summarize_results, summary_to_dict,
)
from scripts.eval.rag_generalization import (
    build_run_id, render_summary_markdown, results_payload, sanitize_results_payload,
)
from scripts.eval.run_rag_eval import _override_case
from scripts.eval.run_rag_generalization_eval import _case_for_temp_kb


def _ranked(ids):
    return ranked_document_snapshot([
        SimpleNamespace(document_id=identity, document_name=f"doc-{identity}.txt", score=0.9)
        for identity in ids
    ])


def _evidence(text="alpha beta", document_id=1, page_number=None):
    return RetrievedEvidence(
        document_id=document_id,
        document_name=f"doc-{document_id}.txt",
        chunk_id=f"{document_id}:0",
        citation_unit_id=document_id,
        text=text,
        source_locator=f"page:{page_number}" if page_number else "chars:0-10",
        page_number=page_number,
        final_score=0.9,
    )


@pytest.mark.parametrize(("ids", "k", "expected", "value"), [
    ([1, 2, 3], 1, (1,), 1.0),
    ([2, 3, 1], 1, (1,), 0.0),
    ([2, 3, 1], 3, (1,), 1.0),
    ([2, 3], 5, (1,), 0.0),
    ([1, 2, 3], 3, (1, 3), 1.0),
    ([1, 2, 3], 1, (1, 3), 0.5),
    ([1, 2, 3], 1, (1, 2, 3), 1 / 3),
    ([1, 1, 2, 3], 3, (1, 3, 3), 1.0),
])
def test_document_recall(ids, k, expected, value):
    assert calculate_document_recall(_ranked(ids), expected_doc_ids=expected, k=k) == pytest.approx(value)


@pytest.mark.parametrize(("ids", "value"), [
    ([1, 2, 3, 4], 1.0), ([2, 1, 3, 4], 0.5), ([2, 3, 4, 1], 0.25), ([2, 3, 4], 0.0),
])
def test_document_mrr(ids, value):
    assert calculate_document_mrr(_ranked(ids), expected_doc_ids=(1,)) == value


def test_document_identity_prefers_ids_and_names_remain_case_insensitive():
    ranked = _ranked([2, 1])
    assert calculate_document_recall(ranked, expected_doc_ids=(1,), expected_doc_names=("doc-2.txt",), k=1) == 0
    assert calculate_document_mrr(ranked, expected_doc_ids=(1,), expected_doc_names=("doc-2.txt",)) == 0.5
    assert calculate_document_mrr(ranked, expected_doc_names=("DOC-1.TXT",)) == 0.5
    assert calculate_document_recall(ranked, k=1) is None
    assert calculate_document_mrr(ranked) is None


@pytest.mark.parametrize(("texts", "phrases", "value"), [
    (["alpha beta gamma"], ("alpha", "beta", "gamma"), 1.0),
    (["alpha gamma"], ("alpha", "beta", "gamma"), 2 / 3),
    (["unrelated"], ("alpha", "beta"), 0.0),
    (["alpha", "alpha"], ("alpha", "beta"), 0.5),
    (["alpha beta"], ("alpha", "**ALPHA**", "beta"), 1.0),
    (["alpha"], (), None),
    (["graph_vector_mix 0.15"], ("`graph_vector_mix`", "0.15。"), 1.0),
])
def test_evidence_recall(texts, phrases, value):
    result = calculate_evidence_recall([_evidence(text) for text in texts], expected_phrases=phrases)
    assert result == pytest.approx(value) if value is not None else result is None


def test_evidence_recall_ignores_phrases_in_unexpected_documents():
    assert calculate_evidence_recall(
        [_evidence("alpha", document_id=2)], expected_phrases=("alpha",), expected_doc_ids=(1,),
    ) == 0


def test_new_document_metrics_use_raw_retrieval_and_evidence_recall_uses_final_evidence():
    case = RagEvalCase(
        id="ranked", question="q", knowledge_base_id=1,
        expected_doc_ids=(1,), expected_evidence_phrases=("alpha", "beta", "gamma"),
    )
    result = RetrievalResult(
        query="q", mode=RetrievalMode.CHUNK_ONLY, context_text="alpha beta gamma",
        evidences=[_evidence("alpha gamma")], trace_id=1,
        metadata={"initial_chunks": _ranked([2, 2, 3, 4, 1]), "context_chunks": []},
    )
    evaluated = evaluate_retrieval_result(case, result)
    assert evaluated.document_recall_at_1 == 0
    assert evaluated.document_recall_at_3 == 0
    assert evaluated.document_recall_at_5 == 1
    assert evaluated.document_mrr == 0.25
    assert evaluated.evidence_recall == pytest.approx(2 / 3)
    assert evaluated.top_1_doc_hit is True  # Legacy metric still ranks final evidence.
    assert evaluated.expected_evidence_hit is True  # Legacy any-phrase hit remains unchanged.
    assert evaluated.document_ranking_source == "initial_chunks"
    assert [item["rank"] for item in evaluated.ranked_retrieved_documents] == [1, 2, 3, 4]


def test_no_answer_denominators_and_missing_ranking_are_explicit():
    case = RagEvalCase(
        id="case", question="q", knowledge_base_id=1, expected_doc_ids=(1,),
        expected_evidence_phrases=("alpha", "beta"), document_format="txt",
    )
    result = RetrievalResult(
        query="q", mode=RetrievalMode.CHUNK_ONLY, context_text="alpha", evidences=[_evidence("alpha")],
        metadata={"initial_chunks": _ranked([1])},
    )
    answerable = evaluate_retrieval_result(case, result)
    no_answer = evaluate_retrieval_result(replace(case, id="absent", expected_answerable=False), result)
    for name in ("document_recall_at_1", "document_recall_at_3", "document_recall_at_5", "document_mrr", "evidence_recall"):
        assert getattr(no_answer, name) is None
    payload = summary_to_dict(summarize_results([answerable, no_answer]))
    assert payload["stage_metrics"]["document_mrr"] == {"mean": 1.0, "applicable": 1}
    assert payload["stage_metrics"]["evidence_recall"] == {"mean": 0.5, "applicable": 1}
    assert payload["by_format"]["txt"]["cases"] == 2
    without_ranking = evaluate_retrieval_result(case, result.model_copy(update={"metadata": {}}))
    assert without_ranking.document_mrr is None
    assert without_ranking.document_ranking_source is None
    assert evaluate_retrieval_result(case, result.model_copy(update={"metadata": {"initial_chunks": []}})).document_mrr == 0
    assert failed_case_result(case, error="failed").document_mrr == 0
    assert failed_case_result(replace(case, expected_answerable=False), error="failed").document_mrr is None


def test_old_schema_defaults_and_new_fields_survive_runner_overrides():
    old = parse_case({"id": "old", "question": "q", "knowledge_base_id": 1})
    assert old.document_format is None and old.expected_page_numbers == ()
    case = replace(old, document_format="pdf", expected_page_numbers=(2,))
    assert _override_case(case, mode="hybrid_text").expected_page_numbers == (2,)
    rewritten = _case_for_temp_kb(case, knowledge_base_id=7, user_id=8, mode="auto")
    assert rewritten.document_format == "pdf" and rewritten.expected_page_numbers == (2,)
    with pytest.raises(ValueError, match="physical page"):
        parse_case({"id": "invalid", "question": "q", "knowledge_base_id": 1, "expected_page_numbers": [0]})


def test_pdf_page_expectation_checks_matching_citation_ready_evidence():
    case = RagEvalCase(
        id="page", question="q", knowledge_base_id=1, expected_doc_ids=(1,),
        expected_evidence_phrases=("alpha",), expected_page_numbers=(2,), document_format="pdf",
    )
    result = RetrievalResult(
        query="q", mode=RetrievalMode.CHUNK_ONLY, context_text="alpha", evidences=[_evidence("alpha", page_number=2)],
    )
    assert evaluate_retrieval_result(case, result).page_provenance_hit is True
    for evidence in (_evidence("alpha", page_number=1), _evidence("unrelated", page_number=2),
                     _evidence("alpha", page_number=2).model_copy(update={"citation_unit_id": None})):
        evaluation = evaluate_retrieval_result(case, result.model_copy(update={"evidences": [evidence]}))
        assert evaluation.page_provenance_hit is False
        assert "page_provenance_miss" in evaluation.failure_reasons


def test_serialization_markdown_and_per_format_aggregation():
    results = []
    for fmt in ("txt", "markdown", "docx", "pdf"):
        case = RagEvalCase(
            id=fmt, question="q | fact", knowledge_base_id=1, document_format=fmt,
            expected_doc_ids=(1,), expected_evidence_phrases=("alpha",),
        )
        results.append(evaluate_retrieval_result(case, RetrievalResult(
            query="q", mode=RetrievalMode.CHUNK_ONLY, context_text="alpha", evidences=[_evidence()],
            metadata={"initial_chunks": _ranked([1])}, trace_id=1,
        ), retrieval_latency_ms=2, total_eval_latency_ms=9))
    results[0] = replace(results[0], failure_reasons=("forbidden_evidence_selected",))
    payload = json.loads(json.dumps(results_payload(results)))
    assert set(payload["by_format"]) == {"txt", "markdown", "docx", "pdf"}
    for group in payload["by_format"].values():
        assert group["cases"] == 1
        assert group["document_recall_at_5"] == {"mean": 1.0, "applicable": 1}
    assert payload["cases"][0]["ranked_retrieved_documents"][0] == {
        "rank": 1, "document_id": 1, "document_name": "doc-1.txt", "score": 0.9,
    }
    metadata = {
        "suite": "format", "run_id": "test", "created_at": "test", "commit_sha": "test", "dirty_worktree": True,
        "case_file": "cases", "case_count": 4, "chunk_strategy": "block_aware", "requested_mode": "auto",
        "embedding_provider": "local_hashed_bow", "embedding_model": "hashed_bow_v1", "reranker_provider": "noop", "reranker_enabled": False,
    }
    markdown = render_summary_markdown(run_metadata=metadata, results=results)
    assert "Format Eval Summary" in markdown and "Metrics by Document Format" in markdown
    for name in ("document_recall_at_1", "document_recall_at_3", "document_recall_at_5", "document_mrr", "evidence_recall"):
        assert name in markdown
    assert "1.000 (n=4)" in markdown
    assert "| retrieval | 2.0 | 2 | 2 | 2 | 4 |" in markdown
    assert "| total eval | 9.0 | 9 | 9 | 9 | 4 |" in markdown
    assert "q \\| fact" in markdown
    sanitized = sanitize_results_payload(payload)
    assert sanitized["stage_metrics"] == payload["stage_metrics"]
    assert sanitized["by_format"] == payload["by_format"]
    assert "document_id" not in sanitized["cases"][0]["ranked_retrieved_documents"][0]


def test_format_run_ids_do_not_collide_with_official_suite():
    timestamp = datetime(2026, 10, 5, tzinfo=UTC)
    options = {"mode": "auto", "chunk_strategy": "block_aware", "created_at": timestamp}
    assert build_run_id(**options) == "20261005-000000-auto-block_aware"
    assert build_run_id(**options, suite="format") == "format-20261005-000000-auto-block_aware"
