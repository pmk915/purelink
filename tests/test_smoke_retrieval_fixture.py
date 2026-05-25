from __future__ import annotations

from pathlib import Path


PRIMARY_SMOKE_QUERY = (
    "PureLink personal knowledge bases team knowledge bases "
    "document retrieval citation smoke test"
)
FALLBACK_SMOKE_QUERY = "AI-powered knowledge platform personal flow smoke document"


def test_personal_smoke_fixture_contains_stable_retrieval_terms() -> None:
    fixture_text = Path("tests/fixtures/personal_sample.txt").read_text(encoding="utf-8").lower()

    for term in [
        "purelink",
        "personal knowledge bases",
        "team knowledge bases",
        "document retrieval",
        "citation",
        "smoke test",
    ]:
        assert term in fixture_text


def test_personal_smoke_queries_overlap_fixture_terms() -> None:
    fixture_text = Path("tests/fixtures/personal_sample.txt").read_text(encoding="utf-8").lower()

    for query in [PRIMARY_SMOKE_QUERY, FALLBACK_SMOKE_QUERY]:
        query_terms = {
            token
            for token in query.lower().replace("-", " ").split()
            if len(token) >= 4
        }
        matched_terms = {token for token in query_terms if token in fixture_text}
        assert len(matched_terms) >= 4
