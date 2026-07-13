from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.core import config


ROOT_DIR = Path(__file__).resolve().parents[2]
CASE_PATH = ROOT_DIR / "tests/eval/rag_generalization_cases.jsonl"
CORPUS_PATH = ROOT_DIR / "tests/eval/corpus/purelink_retrieval.txt"
ENV_EXAMPLE_PATH = ROOT_DIR / ".env.example"
TARGET_CASE_ID = "tech_retrieval_min_score"
EXPECTED_DEFAULT = "0.15"
NON_TARGET_CASES_SHA256 = "09bb5a858eac159687e430f257815b5c555ad9d6018e0f29f2fd84f38f8fc811"


def _load_case_payloads() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in CASE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _target_case() -> dict[str, object]:
    return next(item for item in _load_case_payloads() if item["id"] == TARGET_CASE_ID)


def _env_example_value(name: str) -> str:
    prefix = f"{name}="
    return next(
        line.removeprefix(prefix).strip()
        for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith(prefix)
    )


def test_generalization_cases_are_valid_jsonl_and_keep_non_target_cases_unchanged() -> None:
    cases = _load_case_payloads()

    assert len(cases) == 50
    assert len({str(item["id"]) for item in cases}) == 50
    non_target_cases = [item for item in cases if item["id"] != TARGET_CASE_ID]
    normalized = json.dumps(
        non_target_cases,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert hashlib.sha256(normalized.encode("utf-8")).hexdigest() == NON_TARGET_CASES_SHA256


def test_retrieval_min_score_case_checks_the_default_value_fact() -> None:
    case = _target_case()

    assert "默认值" in str(case["question"])
    assert case["expected_keywords"] == ["RETRIEVAL_MIN_SCORE", EXPECTED_DEFAULT]
    assert case["expected_evidence_phrases"] == [
        "RETRIEVAL_MIN_SCORE defaults to 0.15"
    ]
    assert case["expected_answerable"] is True
    assert case["expected_mode"] == "hybrid_text"
    assert case["expected_citation_required"] is True
    assert case["expected_doc_names"] == [
        "tests/eval/corpus/purelink_retrieval.txt"
    ]


def test_retrieval_corpus_contains_the_expected_default_value_fact() -> None:
    corpus = CORPUS_PATH.read_text(encoding="utf-8")

    assert "`RETRIEVAL_MIN_SCORE` defaults to `0.15`." in corpus
    assert "minimum retrieval score used by answer generation reliability checks" in corpus
    assert "Low-scoring or missing evidence can trigger" in corpus


def test_retrieval_corpus_default_matches_settings_and_env_example(
    monkeypatch,
) -> None:
    monkeypatch.delenv("RETRIEVAL_MIN_SCORE", raising=False)
    monkeypatch.setattr(config, "_load_env_file", lambda: None)
    config.get_settings.cache_clear()
    try:
        settings_default = config.get_settings().retrieval_min_score
    finally:
        config.get_settings.cache_clear()

    env_default = _env_example_value("RETRIEVAL_MIN_SCORE")
    corpus = CORPUS_PATH.read_text(encoding="utf-8")
    assert str(settings_default) == EXPECTED_DEFAULT
    assert env_default == EXPECTED_DEFAULT
    assert f"defaults to `{settings_default}`" in corpus
