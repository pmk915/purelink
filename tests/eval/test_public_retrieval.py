from __future__ import annotations

import json
import math

import pytest

from scripts.eval.public_retrieval import (
    ENGLISH_MODEL, METRICS, aggregate_results, benchmark_environment,
    canonical_qrels, capture_config, convert_corpus, corpus_text,
    evaluate_rankings, ranking_scores,
    purelink_index, purelink_rankings, select_task_names,
)
from scripts.eval.run_public_retrieval import write_report


def test_partial_task_scope_preserves_predefined_order_and_marks_exclusions(tmp_path):
    names = [f"task-{number}" for number in range(13)]
    assert select_task_names(names) == names
    assert select_task_names(names, 6) == names[:6]
    assert select_task_names(names, 20) == names
    for invalid in (0, -1):
        with pytest.raises(ValueError, match="positive"):
            select_task_names(names, invalid)
    metrics = {metric: 0.5 for metric in METRICS}
    report = {"config": {"baseline_sha": "b", "commit_sha": "c", "dirty": True, "retrieval_modes": ["dense"]},
              "tasks": [{"task": name, "results": {"dense": {"status": "completed", "metrics": metrics}
                        if number < 6 else {"status": "not_run", "reason": "Explicit task limit 6"}}}
                        for number, name in enumerate(names)]}
    write_report(tmp_path, report)
    saved = json.loads((tmp_path / "run.json").read_text())
    assert saved["aggregate"]["shared_completed_tasks"] == names[:6]
    assert saved["aggregate"]["excluded_tasks"] == names[6:]
    assert "not_run" in (tmp_path / "summary.md").read_text()
    assert "Explicit task limit 6" in (tmp_path / "summary.md").read_text()


@pytest.mark.parametrize("record,expected", [
    ({"title": "Title", "text": "Body"}, "Title\nBody"),
    ({"text": "Body"}, "Body"), ({"title": "Title", "text": ""}, "Title"),
    ({"title": None, "text": "Body"}, "Body"),
    ({"title": " title ", "text": " body "}, " title \n body "),
])
def test_corpus_representation(record, expected):
    assert corpus_text(record) == expected
    assert convert_corpus({7: record})["7"]["text"] == expected


def test_invalid_corpus_and_canonical_duplicates():
    with pytest.raises(ValueError, match="strings"):
        corpus_text({"text": ["not text"]})
    with pytest.raises(ValueError, match="Duplicate"):
        convert_corpus({1: {"text": "a"}, "1": {"text": "b"}})


def test_qrel_ids_and_grades_are_preserved():
    assert canonical_qrels({1: {2: 2, 3: 0, 4: -1}}) == {"1": {"2": 2.0, "3": 0.0, "4": -1.0}}
    with pytest.raises(ValueError):
        canonical_qrels({"q": {"d": float("nan")}})
    with pytest.raises(ValueError):
        canonical_qrels({"q": {1: 1, "1": 2}})


def test_ranking_dedup_serialization_and_cutoff():
    scores = ranking_scores([1, "1", "b", "c"], top_k=2)
    assert list(scores) == ["1", "b"]
    assert scores["1"] > scores["b"]
    assert json.loads(json.dumps(scores)) == scores


def test_graded_ndcg_recall_mrr_and_missing_relevant_doc():
    result = evaluate_rankings({"q": {"a": 2, "b": 1, "missing": 1}}, {"q": ["unknown", "a", "a", "b"]})
    ideal = 2 + 1 / math.log2(3) + 1 / math.log2(4)
    assert result["ndcg_at_10"] == pytest.approx((2 / math.log2(3) + 1 / math.log2(4)) / ideal)
    assert result["recall_at_10"] == pytest.approx(2 / 3)
    assert result["recall_at_5"] == pytest.approx(2 / 3)
    assert result["mrr_at_10"] == 0.5


def test_metric_cutoffs_missing_queries_and_nonpositive_judgments():
    result = evaluate_rankings({"hit": {"a": 1}, "miss": {"b": 1}, "zero": {"x": 0}}, {"hit": [str(i) for i in range(10)] + ["a"], "zero": ["x"]})
    assert all(value == 0 for value in result.values())
    result = evaluate_rankings({"q": {"a": 1}, "missing": {"b": 1}}, {"q": ["a"]})
    assert all(value == 0.5 for value in result.values())


def test_macro_uses_only_shared_completed_tasks():
    metrics = {metric: 0.5 for metric in METRICS}
    tasks = [
        {"task": "shared", "results": {mode: {"status": "completed", "metrics": metrics} for mode in ["official", "dense"]}},
        {"task": "failed", "results": {"official": {"status": "completed", "metrics": {metric: 1.0 for metric in METRICS}}, "dense": {"status": "failed", "reason": "runtime"}}},
    ]
    result = aggregate_results(tasks, ["official", "dense"])
    assert result["shared_completed_tasks"] == ["shared"]
    assert result["excluded_tasks"] == ["failed"]
    assert result["macro_mean"]["official"]["ndcg_at_10"] == 0.5
    assert aggregate_results([], ["dense"])["macro_mean"]["dense"]["mrr_at_10"] is None


def test_scoped_profile_and_sanitized_config(monkeypatch, tmp_path):
    monkeypatch.setenv("EMBEDDING_MODEL", "demo-model")
    monkeypatch.setenv("EMBEDDING_API_KEY", "secret-must-not-appear")
    monkeypatch.setattr("scripts.eval.public_retrieval.subprocess.check_output", lambda args, **kwargs: "a" * 40 if "rev-parse" in args else " M source.py")
    with benchmark_environment(tmp_path):
        from app.core.config import get_settings
        assert get_settings().embedding_model == ENGLISH_MODEL
        config = capture_config(tmp_path, modes=["official", "dense"], tasks=["synthetic"], baseline_sha="b" * 40)
        assert config["dirty"] is True
        assert len(config["commit_sha"]) == 40
        assert config["embedding_dimension"] == 384
        assert config["normalization"] is True
        assert config["reranker"]["enabled"] is False
        assert "secret-must-not-appear" not in json.dumps(config)
    assert get_settings().embedding_model == "demo-model"
    get_settings.cache_clear()


def test_report_serializes_failures_and_macro(tmp_path):
    report = {"config": {"baseline_sha": "b", "commit_sha": "c", "dirty": True, "retrieval_modes": ["dense"]},
              "tasks": [{"task": "synthetic", "results": {"dense": {"status": "failed", "reason": "unavailable"}}}]}
    write_report(tmp_path, report)
    assert json.loads((tmp_path / "run.json").read_text())["aggregate"]["excluded_tasks"] == ["synthetic"]
    assert "unavailable" in (tmp_path / "summary.md").read_text()


def test_adapter_uses_real_production_dense_and_hybrid(monkeypatch):
    from app.services.embedding_provider import LocalHashedBowEmbeddingProvider
    from app.services.retrieval import hybrid_text_retriever

    provider = LocalHashedBowEmbeddingProvider(default_dimension=128)
    monkeypatch.setattr("app.services.document_embedding._resolve_provider", lambda scheme: provider)
    original_merge = hybrid_text_retriever.merge_hybrid_text_candidates
    calls = []

    def merge(**kwargs):
        calls.append(kwargs)
        return original_merge(**kwargs)

    monkeypatch.setattr(hybrid_text_retriever, "merge_hybrid_text_candidates", merge)
    corpus = {"official-b": {"title": "Beta", "text": "beta"}, "official-a": {"title": "Alpha", "text": "alpha"}}
    with purelink_index(corpus, provider) as index:
        dense = purelink_rankings(index, {"q": "alpha"}, mode="dense")
        hybrid = purelink_rankings(index, {"q": "alpha"}, mode="hybrid")
        assert dense["q"][0] == "official-a"
        assert hybrid["q"][0] == "official-a"
        assert len(hybrid["q"]) == len(set(hybrid["q"]))
        assert calls and calls[0]["vector_candidates"] and calls[0]["keyword_candidates"]
        assert evaluate_rankings({"q": {"official-a": 1}}, dense)["ndcg_at_10"] == 1


def test_adapter_does_not_report_keyword_fallback_as_hybrid(monkeypatch):
    from app.services.embedding_provider import LocalHashedBowEmbeddingProvider
    from app.services.retrieval.hybrid_text_retriever import HybridTextRetrievalMetadata

    provider = LocalHashedBowEmbeddingProvider()
    monkeypatch.setattr("app.services.retrieval.hybrid_text_retriever.retrieve_hybrid_text_chunks", lambda **kwargs: ([], HybridTextRetrievalMetadata(0, keyword_failed=True)))
    with purelink_index({"d": {"text": "alpha"}}, provider) as index:
        with pytest.raises(RuntimeError, match="keyword branch failed"):
            purelink_rankings(index, {"q": "alpha"}, mode="hybrid")


def test_metrics_match_optional_trec_oracle():
    pytrec_eval = pytest.importorskip("pytrec_eval")
    qrels = {"q": {"a": 2, "b": 1, "missing": 1}, "miss": {"c": 1}}
    rankings = {"q": ["unknown", "a", "a", "b"], "miss": ["unknown"]}
    oracle = pytrec_eval.RelevanceEvaluator(qrels, {"ndcg_cut.10", "recall.10", "recip_rank"}).evaluate({qid: ranking_scores(ids) for qid, ids in rankings.items()})
    measured = evaluate_rankings(qrels, rankings)
    for ours, theirs in [("ndcg_at_10", "ndcg_cut_10"), ("recall_at_10", "recall_10"), ("mrr_at_10", "recip_rank")]:
        assert measured[ours] == pytest.approx(sum(row[theirs] for row in oracle.values()) / len(oracle))
