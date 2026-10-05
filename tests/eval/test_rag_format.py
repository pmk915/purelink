from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path

from app.services.document_parsing import get_parser
from scripts.eval.rag_eval import load_cases
from scripts.eval.rag_format import generate_format_corpus
from scripts.eval.run_rag_eval_baseline import _baseline_environment
from scripts.eval.run_rag_generalization_eval import run_generalization_cases


SPEC = Path("tests/eval/format_corpus.json")
CASES = Path("tests/eval/rag_format_cases.jsonl")


def test_format_case_distribution_and_reproducible_small_corpus(tmp_path):
    cases = load_cases(CASES)
    assert len(cases) == 24 and len({case.id for case in cases}) == 24
    assert Counter(case.document_format for case in cases) == {"txt": 6, "markdown": 6, "docx": 6, "pdf": 6}
    assert Counter(case.category for case in cases) == {
        "technical": 4, "factual_lookup": 4, "section_scoped": 4,
        "distractor_sensitive": 4, "structured_fact": 4, "no_answer": 4,
    }
    first = generate_format_corpus(SPEC, tmp_path / "first", cases)
    second = generate_format_corpus(SPEC, tmp_path / "second", cases)
    assert first == second and len(first) == 8
    assert all(document["size_bytes"] < 10000 for document in first)
    for document in first:
        name = document["name"]
        parsed = get_parser(filename=name).parse(tmp_path / "first" / name, filename=name)
        assert parsed.blocks and parsed.text
    pdf_cases = [case for case in cases if case.expected_page_numbers]
    assert len(pdf_cases) == 2
    assert all(case.expected_page_numbers == (2,) and case.expected_citation_required for case in pdf_cases)


def test_format_slice_uses_shared_ingestion_index_retrieval_qa_and_reporting_path(tmp_path):
    cases = load_cases(CASES)
    manifest = generate_format_corpus(SPEC, tmp_path / "corpus", cases)
    with _baseline_environment(
        chunk_strategy="block_aware", upload_root=tmp_path / "uploads",
        vector_root=tmp_path / "vector_store", chunks_root=tmp_path / "chunks",
    ):
        results = asyncio.run(run_generalization_cases(
            cases=cases, source_paths=tuple(item["name"] for item in manifest), mode="auto",
            root=tmp_path, source_root=tmp_path / "corpus",
        ))
    assert len(results) == 24
    assert all(result.error is None for result in results)
    assert all(result.document_ranking_source == "initial_chunks" for result in results)
    assert all(result.trace_available and result.answer_policy_outcome is not None for result in results)
    assert all(result.document_mrr is None for result in results if result.expected_answerable is False)
    # Measurement plumbing is the assertion; retrieval failures remain baseline data.
    assert all(result.page_provenance_hit is not None for result in results if result.expected_page_numbers)
