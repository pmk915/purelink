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
    classify_failure_stage,
    case_result_to_dict,
    evaluate_retrieval_result,
    failed_case_result,
    get_final_evidences,
    load_cases,
    normalize_eval_text,
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


def test_expected_evidence_normalizes_presentation_only_formatting() -> None:
    evidences = [
        _evidence(
            document_id=1,
            document_name="technical.txt",
            text="CHUNK_STRATEGY supports fixed and block_aware. FastAPI uses Depends to inject values.",
        )
    ]

    for phrase in (
        "`CHUNK_STRATEGY` supports `fixed` and `block_aware`.",
        "chunk_strategy SUPPORTS fixed AND block_aware",
        "CHUNK_STRATEGY   supports   fixed   and   block_aware",
        "“CHUNK_STRATEGY” supports fixed and block_aware。",
        "**CHUNK_STRATEGY** supports *fixed* and `block_aware`",
    ):
        assert calculate_expected_evidence_hit(
            evidences,
            expected_doc_names=("technical.txt",),
            expected_phrases=(phrase,),
        )


def test_expected_evidence_normalization_preserves_technical_semantics() -> None:
    evidences = [
        _evidence(
            document_id=1,
            document_name="technical.txt",
            text=(
                "docker compose down preserves volumes. CHUNKSTRATEGY is unrelated. "
                "GET /api/v1/jobs returns ten items and the threshold is 0.15."
            ),
        )
    ]

    for phrase in (
        "docker compose down -v",
        "CHUNK_STRATEGY",
        "GET /api/v2/jobs",
        "threshold is 0.10",
    ):
        assert calculate_expected_evidence_hit(
            evidences,
            expected_doc_names=("technical.txt",),
            expected_phrases=(phrase,),
        ) is False


def test_normalize_eval_text_keeps_identifiers_paths_flags_and_numbers() -> None:
    normalized = normalize_eval_text(
        "`CHUNK_STRATEGY` GET /api/v1/jobs docker compose down -v 0.15。"
    )

    assert normalized == "chunk_strategy get /api/v1/jobs docker compose down -v 0.15"


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


def test_answerability_accuracy_uses_support_gate_for_no_answer() -> None:
    case = RagEvalCase(
        id="no-answer",
        question="Acme CEO?",
        knowledge_base_id=1,
        expected_answerable=False,
    )
    result = RetrievalResult(
        query=case.question,
        mode=RetrievalMode.CHUNK_ONLY,
        evidences=[_evidence(document_id=1, document_name="policy.txt", text="Acme employee policy covers holidays.")],
        context_text="policy",
        trace_id=1,
    )

    evaluated = evaluate_retrieval_result(case, result)

    assert evaluated.predicted_answerable is False
    assert evaluated.answerability_accuracy is True
    assert evaluated.evidence_support_reason == "missing_attribute_support"
    assert "unexpected_answerable" not in evaluated.failure_reasons


def test_answerability_support_gate_accepts_supported_evidence() -> None:
    case = RagEvalCase(
        id="answerable",
        question="Alice Chen 在哪里办公？",
        knowledge_base_id=1,
        expected_answerable=True,
    )
    result = RetrievalResult(
        query=case.question,
        mode=RetrievalMode.CHUNK_ONLY,
        evidences=[
            _evidence(
                document_id=1,
                document_name="roles.txt",
                text="Alice Chen 的办公地点：Singapore。",
                final_score=0.05,
            )
        ],
        context_text="Alice Chen 的办公地点：Singapore。",
        trace_id=1,
    )

    evaluated = evaluate_retrieval_result(case, result, retrieval_min_score=0.15)

    assert evaluated.predicted_answerable is True
    assert evaluated.answerability_accuracy is True
    assert evaluated.evidence_support_reason == "supported"


def test_answer_policy_observability_is_extracted_and_serialized() -> None:
    case = RagEvalCase(
        id="answer-policy-supported",
        question="What is supported?",
        knowledge_base_id=1,
        expected_answerable=True,
    )
    result = RetrievalResult(
        query=case.question,
        mode=RetrievalMode.CHUNK_ONLY,
        evidences=[_evidence(document_id=1, document_name="doc.md")],
        context_text="supported evidence",
        trace_id=1,
        metadata={
            "answer_policy_outcome": "answer",
            "answer_policy_reason": "supported",
            "answer_provider_called": True,
            "answer_citation_required": True,
            "answer_external_knowledge_allowed": False,
            "answer_allowed_evidence_count": 2,
            "answer_allowed_markers": ["S1", "S2"],
            "answer_unknown_markers_removed": 3,
        },
    )

    evaluated = evaluate_retrieval_result(case, result)
    payload = case_result_to_dict(evaluated)

    assert evaluated.answer_policy_outcome == "answer"
    assert evaluated.answer_policy_reason == "supported"
    assert evaluated.answer_provider_called is True
    assert evaluated.answer_citation_required is True
    assert evaluated.answer_external_knowledge_allowed is False
    assert evaluated.answer_allowed_evidence_count == 2
    assert evaluated.answer_allowed_markers == ["S1", "S2"]
    assert evaluated.answer_unknown_markers_removed == 3
    assert payload["answer_policy_outcome"] == "answer"
    assert payload["answer_policy_reason"] == "supported"
    assert payload["answer_provider_called"] is True
    assert payload["answer_citation_required"] is True
    assert payload["answer_external_knowledge_allowed"] is False
    assert payload["answer_allowed_evidence_count"] == 2
    assert payload["answer_allowed_markers"] == ["S1", "S2"]
    assert payload["answer_unknown_markers_removed"] == 3


def test_answer_policy_observability_handles_refusal_missing_and_invalid_metadata() -> None:
    refusal_case = RagEvalCase(
        id="answer-policy-refusal",
        question="Missing fact?",
        knowledge_base_id=1,
        expected_answerable=False,
    )
    refusal = evaluate_retrieval_result(
        refusal_case,
        RetrievalResult(
            query=refusal_case.question,
            mode=RetrievalMode.CHUNK_ONLY,
            evidences=[],
            context_text="",
            trace_id=1,
            metadata={
                "answer_policy_outcome": "refuse",
                "answer_policy_reason": "evidence_support_rejected",
                "answer_provider_called": False,
                "answer_citation_required": False,
                "answer_external_knowledge_allowed": False,
                "answer_allowed_evidence_count": 0,
                "answer_allowed_markers": "S1",
                "answer_unknown_markers_removed": 0,
            },
        ),
    )
    legacy = failed_case_result(refusal_case, error="legacy failure")

    assert refusal.answer_policy_outcome == "refuse"
    assert refusal.answer_provider_called is False
    assert refusal.answer_citation_required is False
    assert refusal.answer_allowed_markers == []
    assert refusal.answer_unknown_markers_removed == 0
    legacy_payload = case_result_to_dict(legacy)
    assert legacy_payload["answer_policy_outcome"] is None
    assert legacy_payload["answer_provider_called"] is None
    assert legacy_payload["answer_allowed_markers"] == []


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


def test_failure_stage_distinguishes_retrieval_context_selection_and_support() -> None:
    expected = _evidence(
        document_id=1,
        document_name="runtime.txt",
        text="REQUEST_TIMEOUT_SECONDS controls waiting.",
    )
    unrelated = _evidence(document_id=2, document_name="other.txt", text="Other fact.")
    case = RagEvalCase(
        id="stage",
        question="REQUEST_TIMEOUT_SECONDS 的默认值是多少？",
        knowledge_base_id=1,
        expected_doc_names=("runtime.txt",),
        expected_evidence_phrases=("REQUEST_TIMEOUT_SECONDS controls waiting",),
        expected_answerable=True,
    )

    retrieval_miss = evaluate_retrieval_result(
        case,
        _retrieval_result(evidences=[], initial=[unrelated], context=[unrelated]),
    )
    raw_candidate_miss = evaluate_retrieval_result(
        case,
        _retrieval_result(
            evidences=[],
            initial=[_evidence(document_id=1, document_name="runtime.txt", text="Unrelated runtime fact.")],
            context=[],
        ),
    )
    context_miss = evaluate_retrieval_result(
        case,
        _retrieval_result(evidences=[], initial=[expected], context=[unrelated]),
    )
    selection_miss = evaluate_retrieval_result(
        case,
        _retrieval_result(evidences=[unrelated], initial=[expected], context=[expected]),
    )
    support_miss = evaluate_retrieval_result(
        case,
        _retrieval_result(evidences=[expected], initial=[expected], context=[expected]),
    )

    assert retrieval_miss.failure_stage == "retrieval_document_miss"
    assert raw_candidate_miss.failure_stage == "raw_candidate_miss"
    assert context_miss.failure_stage == "final_context_miss"
    assert selection_miss.failure_stage == "evidence_selection_miss"
    assert support_miss.failure_stage == "support_gate_miss"


def test_failure_stage_records_success_format_mismatch_and_genuine_no_answer() -> None:
    formatted = _evidence(
        document_id=1,
        document_name="runtime.txt",
        text="CHUNK_STRATEGY supports fixed and block_aware values.",
    )
    formatted_case = RagEvalCase(
        id="format",
        question="CHUNK_STRATEGY 支持哪些值？",
        knowledge_base_id=1,
        expected_doc_names=("runtime.txt",),
        expected_evidence_phrases=("supports `fixed` and `block_aware` values",),
        expected_answerable=True,
    )
    format_result = evaluate_retrieval_result(
        formatted_case,
        _retrieval_result(evidences=[formatted], initial=[formatted], context=[formatted]),
    )
    success_case = RagEvalCase(
        id="success",
        question="CHUNK_STRATEGY 支持哪些值？",
        knowledge_base_id=1,
        expected_doc_names=("runtime.txt",),
        expected_evidence_phrases=("supports fixed and block_aware values",),
        expected_answerable=True,
    )
    success_result = evaluate_retrieval_result(
        success_case,
        _retrieval_result(evidences=[formatted], initial=[formatted], context=[formatted]),
    )
    no_answer_result = evaluate_retrieval_result(
        RagEvalCase(
            id="missing",
            question="Unknown setting default?",
            knowledge_base_id=1,
            expected_answerable=False,
            expected_citation_required=False,
        ),
        _retrieval_result(evidences=[], initial=[], context=[]),
    )

    assert format_result.failure_stage == "expected_phrase_format_mismatch"
    assert success_result.failure_stage == "success"
    assert no_answer_result.failure_stage == "genuine_no_answer"
    assert classify_failure_stage(
        expected_answerable=False,
        predicted_answerable=True,
        expected_document_in_raw_candidates=None,
        expected_evidence_in_raw_candidates=None,
        expected_document_in_final_context=None,
        expected_evidence_in_final_context=None,
        expected_document_in_final_selection=None,
        expected_evidence_in_final_selection=None,
        literal_expected_evidence_hit=None,
    ) == "support_gate_miss"


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
    assert "## 7. Failure Diagnostics" in markdown
    assert "### Failed Cases" in markdown
    assert "| Failure Stage | Cases |" in markdown
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
    assert "`no-answer` | False | true" in markdown


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
                expected_doc_names=((corpus_dir / "python_classes.txt").as_posix(),),
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
    assert sum(1 for case in cases if case.expected_answerable is True and case.expected_citation_required) == 44
    assert sum(1 for case in cases if case.expected_answerable is False and not case.expected_citation_required) == 6


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
                "user_id": 7,
                "knowledge_base_id": 8,
                "local_path": "/tmp/private/result.json",
                "retrieval_hit": True,
                "citation_hit": True,
                "answer_policy_outcome": "answer",
                "answer_policy_reason": "supported",
                "answer_provider_called": True,
                "answer_citation_required": True,
                "answer_external_knowledge_allowed": False,
                "answer_allowed_evidence_count": 2,
                "answer_allowed_markers": ["S1", "S2", "/tmp/private/S3", "invalid"],
                "answer_unknown_markers_removed": 4,
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
    assert "user_id" not in combined
    assert "knowledge_base_id" not in combined
    assert "local_path" not in combined
    assert sanitized_results["cases"][0]["answer_policy_outcome"] == "answer"
    assert sanitized_results["cases"][0]["answer_policy_reason"] == "supported"
    assert sanitized_results["cases"][0]["answer_provider_called"] is True
    assert sanitized_results["cases"][0]["answer_citation_required"] is True
    assert sanitized_results["cases"][0]["answer_external_knowledge_allowed"] is False
    assert sanitized_results["cases"][0]["answer_allowed_evidence_count"] == 2
    assert sanitized_results["cases"][0]["answer_allowed_markers"] == ["S1", "S2"]
    assert sanitized_results["cases"][0]["answer_unknown_markers_removed"] == 4
    assert "evidence" in combined


def test_sanitized_snapshot_preserves_no_answer_policy_contract() -> None:
    sanitized = sanitize_results_payload(
        {
            "case_count": 1,
            "cases": [
                {
                    "id": "no-answer",
                    "answer_policy_outcome": "refuse",
                    "answer_policy_reason": "evidence_support_rejected",
                    "answer_provider_called": False,
                    "answer_citation_required": False,
                    "answer_external_knowledge_allowed": False,
                    "answer_allowed_evidence_count": 0,
                    "answer_allowed_markers": [],
                    "answer_unknown_markers_removed": 0,
                    "trace_id": 123,
                    "document_id": 456,
                }
            ],
        }
    )

    case = sanitized["cases"][0]
    assert case["answer_policy_outcome"] == "refuse"
    assert case["answer_policy_reason"] == "evidence_support_rejected"
    assert case["answer_provider_called"] is False
    assert case["answer_citation_required"] is False
    assert case["answer_external_knowledge_allowed"] is False
    assert case["answer_allowed_evidence_count"] == 0
    assert case["answer_allowed_markers"] == []
    assert case["answer_unknown_markers_removed"] == 0
    assert "trace_id" not in case
    assert "document_id" not in case


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


def _retrieval_result(
    *,
    evidences: list[RetrievedEvidence],
    initial: list[RetrievedEvidence],
    context: list[RetrievedEvidence],
) -> RetrievalResult:
    return RetrievalResult(
        query="evaluation query",
        mode=RetrievalMode.CHUNK_ONLY,
        evidences=evidences,
        context_text="\n".join(item.text for item in evidences),
        metadata={"initial_chunks": initial, "context_chunks": context},
        trace_id=1,
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
