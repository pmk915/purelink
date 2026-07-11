from __future__ import annotations

from pathlib import Path

from app.services.retrieval.types import RetrievedEvidence, RetrievalMode, RetrievalResult
from scripts.eval.rag_eval import (
    RagEvalCase,
    calculate_evidence_precision,
    calculate_expected_evidence_hit,
    calculate_forbidden_evidence_hit,
    calculate_citation_hit,
    calculate_keyword_coverage,
    calculate_retrieval_hit,
    classify_evidence_units,
    evaluate_retrieval_result,
    get_final_evidences,
    load_cases,
    parse_case,
    summarize_latencies,
    summarize_results,
)
from scripts.eval.rag_generalization import (
    build_run_metadata,
    render_summary_markdown,
    sanitize_results_payload,
    sanitize_run_payload,
    validate_corpus,
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
    ) is None


def test_retrieval_hit_is_null_without_expected_document() -> None:
    assert calculate_retrieval_hit(
        [_evidence(document_id=1, document_name="doc.md")],
        expected_doc_names=(),
    ) is None


def test_citation_hit_requires_canonical_citation_unit_and_locator() -> None:
    assert calculate_citation_hit(
        [
            _evidence(document_id=1, document_name="doc.md", citation_unit_id=10),
            _evidence(document_id=1, document_name="doc.md", citation_unit_id=None),
        ],
        expected_doc_names=("doc.md",),
        expected_citation_required=True,
    ) is True
    assert calculate_citation_hit(
        [_evidence(document_id=1, document_name="doc.md", citation_unit_id=10, source_locator=None)],
        expected_doc_names=("doc.md",),
        expected_citation_required=True,
    ) is False
    assert calculate_citation_hit(
        [
            _evidence(document_id=1, document_name="doc.md", citation_unit_id=None),
            _evidence(document_id=2, document_name="other.md", citation_unit_id=20),
        ],
        expected_doc_names=("doc.md",),
        expected_citation_required=True,
    ) is False


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


def test_parse_case_accepts_generalization_fields() -> None:
    case = parse_case(
        {
            "id": "generalization-case",
            "question": "Alice Chen 在哪里办公？",
            "knowledge_base_id": 1,
            "mode": "auto",
            "category": "entity_attribute",
            "expected_mode": "chunk_only",
            "expected_evidence_phrases": ["办公地点：Singapore"],
            "forbidden_evidence_phrases": ["Shanghai"],
            "expected_answerable": True,
            "notes": "multi-entity attribute",
        }
    )

    assert case.category == "entity_attribute"
    assert case.expected_mode == "chunk_only"
    assert case.expected_evidence_phrases == ("办公地点：Singapore",)
    assert case.forbidden_evidence_phrases == ("Shanghai",)
    assert case.expected_answerable is True


def test_expected_and_forbidden_evidence_hits() -> None:
    evidences = [
        _evidence(document_id=1, document_name="team.md", text="办公地点：Singapore"),
        _evidence(document_id=1, document_name="team.md", text="办公地点：Shanghai"),
    ]

    assert calculate_expected_evidence_hit(
        evidences,
        expected_doc_names=("team.md",),
        expected_phrases=("Singapore",),
    )
    assert calculate_forbidden_evidence_hit(
        evidences,
        forbidden_phrases=("Shanghai",),
    )
    assert calculate_expected_evidence_hit(
        evidences,
        expected_doc_names=("other.md",),
        expected_phrases=("Singapore",),
    ) is False
    assert calculate_forbidden_evidence_hit(evidences, forbidden_phrases=()) is None


def test_evidence_classification_and_precision() -> None:
    evidences = [
        _evidence(document_id=1, document_name="team.md", text="办公地点：Singapore"),
        _evidence(document_id=1, document_name="team.md", text="办公地点：Shanghai"),
        _evidence(document_id=2, document_name="other.md", text="办公地点：Singapore"),
        _evidence(document_id=1, document_name="team.md", text="role details"),
    ]

    classified = classify_evidence_units(
        evidences,
        expected_doc_names=("team.md",),
        expected_phrases=("Singapore",),
        forbidden_phrases=("Shanghai",),
    )

    assert classified == {"relevant": 1, "irrelevant": 2, "unknown": 1}
    assert calculate_evidence_precision(relevant=1, irrelevant=2) == 1 / 3
    assert calculate_evidence_precision(relevant=0, irrelevant=0) is None


def test_router_and_answerability_accuracy_and_failure_reasons() -> None:
    case = RagEvalCase(
        id="auto-case",
        question="总结 Python classes 文档",
        knowledge_base_id=1,
        mode="auto",
        expected_doc_names=("python_classes.txt",),
        expected_evidence_phrases=("Class Definition",),
        expected_mode="overview",
        expected_answerable=True,
    )
    result = RetrievalResult(
        query=case.question,
        mode=RetrievalMode.CHUNK_ONLY,
        requested_mode=RetrievalMode.AUTO,
        selected_mode=RetrievalMode.CHUNK_ONLY,
        evidences=[
            _evidence(document_id=1, document_name="python_classes.txt", text="wrong evidence"),
        ],
        context_text="wrong evidence",
        trace_id=None,
    )

    evaluated = evaluate_retrieval_result(case, result)

    assert evaluated.router_accuracy is False
    assert evaluated.answerability_accuracy is True
    assert "router_mode_mismatch" in evaluated.failure_reasons
    assert "expected_evidence_not_selected" in evaluated.failure_reasons
    assert "trace_missing" in evaluated.failure_reasons


def test_answerability_accuracy_detects_unexpected_answerable() -> None:
    case = RagEvalCase(
        id="no-answer",
        question="Acme CEO?",
        knowledge_base_id=1,
        expected_answerable=False,
    )
    result = RetrievalResult(
        query=case.question,
        mode=RetrievalMode.CHUNK_ONLY,
        evidences=[_evidence(document_id=1, document_name="policy.txt")],
        context_text="policy",
        trace_id=1,
    )

    evaluated = evaluate_retrieval_result(case, result)

    assert evaluated.predicted_answerable is True
    assert evaluated.answerability_accuracy is False
    assert "unexpected_answerable" in evaluated.failure_reasons


def test_answerability_requires_reliable_evidence_score() -> None:
    case = RagEvalCase(
        id="low-score",
        question="Acme CEO?",
        knowledge_base_id=1,
        expected_answerable=False,
    )
    result = RetrievalResult(
        query=case.question,
        mode=RetrievalMode.CHUNK_ONLY,
        evidences=[_evidence(document_id=1, document_name="policy.txt", final_score=0.05)],
        context_text="policy",
        trace_id=1,
    )

    evaluated = evaluate_retrieval_result(case, result, retrieval_min_score=0.15)

    assert evaluated.predicted_answerable is False
    assert evaluated.answerability_accuracy is True
    assert "unexpected_answerable" not in evaluated.failure_reasons


def test_null_metrics_are_not_failure_reasons() -> None:
    case = RagEvalCase(
        id="no-answer",
        question="unknown",
        knowledge_base_id=1,
        expected_citation_required=False,
        expected_answerable=False,
    )
    result = RetrievalResult(
        query=case.question,
        mode=RetrievalMode.CHUNK_ONLY,
        evidences=[],
        context_text="",
        trace_id=1,
    )

    evaluated = evaluate_retrieval_result(case, result)

    assert evaluated.retrieval_hit is None
    assert evaluated.citation_hit is None
    assert evaluated.expected_evidence_hit is None
    assert evaluated.answerability_accuracy is True
    assert evaluated.failure_reasons == ()


def test_final_evidence_uses_retrieval_result_evidences_not_metadata_chunks() -> None:
    final = _evidence(document_id=1, document_name="doc.md", text="final citation unit")
    raw = _evidence(document_id=2, document_name="raw.md", text="raw chunk")
    result = RetrievalResult(
        query="q",
        mode=RetrievalMode.CHUNK_ONLY,
        evidences=[final],
        context_text="final citation unit",
        metadata={
            "initial_chunks": [raw],
            "context_chunks": [raw],
            "evidence_units": [raw],
        },
        trace_id=1,
    )
    case = RagEvalCase(
        id="case",
        question="q",
        knowledge_base_id=1,
        expected_doc_names=("doc.md",),
        expected_evidence_phrases=("final citation unit",),
    )

    evaluated = evaluate_retrieval_result(case, result)

    assert get_final_evidences(result) == (final,)
    assert evaluated.final_evidence_units[0]["text"] == "final citation unit"
    assert evaluated.retrieval_hit is True
    assert evaluated.expected_evidence_hit is True


def test_latency_percentiles() -> None:
    assert summarize_latencies([1, 2, 3, 100]) == {"mean": 26.5, "p50": 2, "p95": 85, "max": 100}


def test_summary_markdown_generation_for_generalization() -> None:
    case = RagEvalCase(
        id="case-1",
        question="q",
        knowledge_base_id=1,
        category="technical",
        expected_doc_names=("doc.md",),
        expected_evidence_phrases=("keyword",),
        expected_answerable=True,
    )
    result = evaluate_retrieval_result(
        case,
        RetrievalResult(
            query="q",
            mode=RetrievalMode.HYBRID_TEXT,
            selected_mode=RetrievalMode.HYBRID_TEXT,
            evidences=[_evidence(document_id=1, document_name="doc.md", text="keyword")],
            context_text="keyword",
            trace_id=1,
        ),
        total_eval_latency_ms=7,
    )
    markdown = render_summary_markdown(
        run_metadata={
            "run_id": "test-run",
            "created_at": "2026-07-11T00:00:00+00:00",
            "commit_sha": "abc123",
            "dirty_worktree": True,
            "case_file": "cases.jsonl",
            "case_count": 1,
            "chunk_strategy": "block_aware",
            "requested_mode": "auto",
            "embedding_provider": "local_hashed_bow",
            "embedding_model": "hashed_bow_v1",
            "reranker_provider": "noop",
            "reranker_enabled": False,
        },
        results=[result],
    )

    assert "## 1. Run Configuration" in markdown
    assert "## 7. Failed Cases" in markdown
    assert "1 / 1 (100.0%)" in markdown
    assert "In-process retrieval latency" in markdown
    assert "Evidence-gate answerability" in markdown
    assert "technical" in markdown


def test_summary_null_metrics_do_not_enter_denominator() -> None:
    answerable = evaluate_retrieval_result(
        RagEvalCase(
            id="answerable",
            question="q",
            knowledge_base_id=1,
            expected_doc_names=("doc.md",),
            expected_citation_required=True,
            expected_answerable=True,
        ),
        RetrievalResult(
            query="q",
            mode=RetrievalMode.CHUNK_ONLY,
            evidences=[_evidence(document_id=1, document_name="doc.md")],
            context_text="q",
            trace_id=1,
        ),
    )
    no_answer = evaluate_retrieval_result(
        RagEvalCase(
            id="no-answer",
            question="missing",
            knowledge_base_id=1,
            category="no_answer",
            expected_citation_required=False,
            expected_answerable=False,
        ),
        RetrievalResult(
            query="missing",
            mode=RetrievalMode.CHUNK_ONLY,
            evidences=[],
            context_text="",
            trace_id=2,
        ),
    )

    markdown = render_summary_markdown(
        run_metadata=_run_metadata(case_count=2),
        results=[answerable, no_answer],
    )

    assert "| retrieval_hit | 1 / 1 (100.0%) |" in markdown
    assert "| citation_hit | 1 / 1 (100.0%) |" in markdown
    assert "`no-answer` | n/a | n/a | n/a | False | true" in markdown


def test_corpus_manifest_validation(tmp_path) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    for filename in (
        "python_classes.txt",
        "fastapi_dependencies.txt",
        "postgresql_concurrency.txt",
        "alice_characters.txt",
        "acme_team_roles.txt",
        "device_catalog.txt",
        "employee_policy.txt",
        "purelink_retrieval.txt",
        "purelink_processing.txt",
    ):
        corpus_dir.joinpath(filename).write_text(
            "# Title\n\n## One\n\n" + ("Safe evaluation text. " * 50) + "\n\n## Two\n\nDone.",
            encoding="utf-8",
        )
    manifest = validate_corpus(
        corpus_dir,
        [
            RagEvalCase(
                id="case",
                question="q",
                knowledge_base_id=1,
                expected_doc_names=("tests/eval/corpus/python_classes.txt",),
            )
        ],
    )

    assert len(manifest) == 9


def test_generalization_cases_have_expected_modes_and_answerability_contracts() -> None:
    cases = load_cases(Path("tests/eval/rag_generalization_cases.jsonl"))

    assert len(cases) == 50
    assert all(case.mode == "auto" for case in cases)
    assert all(case.expected_mode for case in cases)
    assert all(case.expected_answerable is not None for case in cases)
    assert sum(1 for case in cases if case.expected_answerable is True and case.expected_citation_required) == 45
    assert sum(1 for case in cases if case.expected_answerable is False and not case.expected_citation_required) == 5


def test_results_metadata_does_not_include_api_keys() -> None:
    class Settings:
        embedding_provider = "local_hashed_bow"
        embedding_model = "hashed_bow_v1"
        reranker_enabled = False
        reranker_provider = "noop"
        retrieval_min_score = 0.0
        deepseek_api_key = "secret"

    payload = build_run_metadata(
        run_id="run",
        created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        case_file=__import__("pathlib").Path("cases.jsonl"),
        corpus_manifest=[],
        case_count=0,
        chunk_strategy="block_aware",
        requested_mode="auto",
        settings=Settings(),
        duration_ms=1,
    )

    assert "api_key" not in json_text(payload)
    assert "secret" not in json_text(payload)


def test_sanitized_snapshot_removes_live_ids_paths_and_secrets() -> None:
    run_payload = {
        **_run_metadata(case_count=1),
        "corpus_manifest": [
            {
                "name": "doc.txt",
                "path": "/tmp/private/doc.txt",
                "char_count": 1000,
                "heading_count": 3,
                "sha256": "abc",
            }
        ],
        "database_url": "postgresql://secret",
    }
    results_payload = {
        "case_count": 1,
        "cases": [
            {
                "id": "case",
                "question": "q",
                "trace_id": 123,
                "retrieval_hit": True,
                "citation_hit": True,
                "final_evidence_units": [
                    {
                        "document_id": 9,
                        "chunk_id": "9:0",
                        "citation_unit_id": 99,
                        "document_name": "doc.txt",
                        "text": "evidence",
                        "score": 0.9,
                        "source_locator": "section:Doc",
                    }
                ],
            }
        ],
    }

    sanitized_run = sanitize_run_payload(run_payload)
    sanitized_results = sanitize_results_payload(results_payload)
    combined = json_text({"run": sanitized_run, "results": sanitized_results})

    assert "/tmp/private" not in combined
    assert "postgresql://secret" not in combined
    assert "trace_id" not in combined
    assert "document_id" not in combined
    assert "citation_unit_id" not in combined
    assert "chunk_id" not in combined
    assert "evidence" in combined


def _evidence(
    *,
    document_id: int,
    document_name: str | None,
    citation_unit_id: int | None = 1,
    text: str = "evidence text",
    final_score: float | None = None,
    source_locator: str | None = "section:test",
) -> RetrievedEvidence:
    return RetrievedEvidence(
        document_id=document_id,
        chunk_id="chunk-1",
        citation_unit_id=citation_unit_id,
        text=text,
        document_name=document_name,
        final_score=final_score,
        source_locator=source_locator,
    )


def _run_metadata(*, case_count: int) -> dict:
    return {
        "run_id": "test-run",
        "created_at": "2026-07-11T00:00:00+00:00",
        "commit_sha": "abc123",
        "dirty_worktree": True,
        "case_file": "cases.jsonl",
        "case_count": case_count,
        "chunk_strategy": "block_aware",
        "requested_mode": "auto",
        "embedding_provider": "local_hashed_bow",
        "embedding_model": "hashed_bow_v1",
        "reranker_provider": "noop",
        "reranker_enabled": False,
    }


def json_text(value) -> str:  # noqa: ANN001
    import json

    return json.dumps(value, ensure_ascii=False)
