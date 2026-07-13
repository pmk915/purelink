from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.services.retrieval.query_router import route_query
from scripts.eval.rag_eval import load_cases, normalize_eval_text
from scripts.eval.rag_generalization import validate_corpus
from scripts.eval.run_rag_generalization_eval import parse_args


ROOT = Path(__file__).resolve().parents[2]
CASE_PATH = ROOT / "tests/eval/rag_generalization_holdout_cases.jsonl"
CORPUS_DIR = ROOT / "tests/eval/holdout_corpus"


def test_holdout_cases_are_independent_and_cover_required_categories() -> None:
    cases = load_cases(CASE_PATH)

    assert len(cases) == 20
    assert len({case.id for case in cases}) == 20
    assert Counter(case.category for case in cases) == {
        "overview": 5,
        "entity_attribute": 5,
        "technical": 6,
        "no_answer": 4,
    }
    assert all(case.mode == "auto" for case in cases)
    assert all(case.expected_mode for case in cases)
    joined_questions = "\n".join(case.question for case in cases).casefold()
    for debug_entity in ("alice", "aurora mini", "deepseek"):
        assert debug_entity not in joined_questions


def test_holdout_corpus_and_expected_documents_are_valid() -> None:
    cases = load_cases(CASE_PATH)
    manifest = validate_corpus(CORPUS_DIR, cases, required_files=())

    assert len(manifest) == 5
    corpus_paths = {Path(item["path"]).resolve() for item in manifest}
    for case in cases:
        for expected_document in case.expected_doc_names:
            assert (ROOT / expected_document).resolve() in corpus_paths


def test_holdout_expected_phrases_are_grounded_in_fixture_documents() -> None:
    for case in load_cases(CASE_PATH):
        if not case.expected_evidence_phrases:
            continue
        document_text = "\n".join(
            (ROOT / document_name).read_text(encoding="utf-8")
            for document_name in case.expected_doc_names
        )
        normalized_document = normalize_eval_text(document_text)
        for phrase in case.expected_evidence_phrases:
            assert normalize_eval_text(phrase) in normalized_document, (case.id, phrase)


def test_holdout_no_answer_ground_truth_is_absent() -> None:
    corpus = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(CORPUS_DIR.glob("*.txt"))
    )
    normalized = normalize_eval_text(corpus)

    assert "ocean-current-handbook" not in normalized
    assert "vacation entitlement" not in normalized
    assert "leave entitlement" not in normalized
    assert "`pipeline_profiles`" not in corpus.casefold()
    assert "kestrel edge weighs" not in normalized
    assert "kestrel edge weight is" not in normalized
    assert "does not specify the device weight" not in normalized


def test_holdout_expected_router_modes_match_rule_router() -> None:
    for case in load_cases(CASE_PATH):
        assert route_query(case.question).selected_mode.value == case.expected_mode, case.id


def test_runner_accepts_custom_holdout_case_and_corpus_paths() -> None:
    args = parse_args(
        [
            "--cases",
            "tests/eval/rag_generalization_holdout_cases.jsonl",
            "--corpus-dir",
            "tests/eval/holdout_corpus",
            "--run-id",
            "holdout-test",
        ]
    )

    assert args.cases == Path("tests/eval/rag_generalization_holdout_cases.jsonl")
    assert args.corpus_dir == Path("tests/eval/holdout_corpus")
    assert args.run_id == "holdout-test"
