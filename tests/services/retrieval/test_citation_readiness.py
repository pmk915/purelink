from __future__ import annotations

from types import SimpleNamespace

from app.services.retrieval.citation_builder import (
    build_evidences,
    citation_readiness,
    summarize_citation_readiness,
)


def test_build_evidences_propagates_citation_unit_provenance() -> None:
    evidence = build_evidences(
        [
            SimpleNamespace(
                marker="S4",
                document_id=3,
                chunk_id="3:2",
                chunk_db_id=12,
                citation_id=41,
                citation_unit_id=41,
                text="A grounded fact.",
                source_locator="page:3",
                source_type="pdf",
                page_number=3,
                char_start=120,
                char_end=136,
                section_title="Findings",
                heading_path=("Report", "Findings"),
                score=0.92,
            )
        ]
    )[0]

    assert evidence.citation_id == 41
    assert evidence.citation_unit_id == 41
    assert evidence.source_locator == "page:3"
    assert evidence.page_number == 3
    assert (evidence.char_start, evidence.char_end) == (120, 136)
    assert evidence.section_title == "Findings"
    assert evidence.heading_path == ["Report", "Findings"]
    assert evidence.metadata["marker"] == "S4"
    assert citation_readiness(evidence) == (True, "ready")


def test_build_evidences_prefers_ready_duplicate_without_changing_order() -> None:
    fallback = SimpleNamespace(
        document_id=1,
        chunk_id="1:0",
        chunk_db_id=10,
        text="Same grounded fact.",
        source_locator=None,
        score=0.9,
    )
    citation_unit = SimpleNamespace(
        document_id=1,
        chunk_id="1:0",
        chunk_db_id=10,
        citation_id=25,
        citation_unit_id=25,
        text="Same grounded fact.",
        source_locator="section:Facts",
        char_start=20,
        char_end=39,
        score=0.8,
    )

    evidences = build_evidences([fallback, citation_unit])

    assert len(evidences) == 1
    assert evidences[0].citation_unit_id == 25
    assert evidences[0].source_locator == "section:Facts"
    assert evidences[0].metadata["marker"] == "S1"


def test_chunk_fallback_is_not_marked_citation_ready_or_given_fake_unit_id() -> None:
    evidence = build_evidences(
        [
            SimpleNamespace(
                document_id=1,
                chunk_id="1:0",
                chunk_db_id=10,
                text="Chunk-only fallback.",
                source_locator=None,
                score=0.7,
            )
        ]
    )[0]

    assert evidence.citation_unit_id is None
    assert evidence.source_locator is None
    assert citation_readiness(evidence) == (
        False,
        "chunk_fallback_without_locator",
    )
    assert summarize_citation_readiness([evidence]) == {
        "citation_ready_count": 0,
        "citation_missing_count": 1,
        "citation_missing_reasons": {"chunk_fallback_without_locator": 1},
    }


def test_unit_without_stable_locator_remains_not_ready() -> None:
    evidence = build_evidences(
        [
            SimpleNamespace(
                document_id=1,
                chunk_id="1:0",
                chunk_db_id=10,
                citation_unit_id=30,
                text="Unit without source location.",
                source_locator=None,
                score=0.8,
            )
        ]
    )[0]

    assert citation_readiness(evidence) == (False, "missing_source_locator")
