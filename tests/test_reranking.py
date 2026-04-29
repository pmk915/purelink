from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.document_embedding import RetrievedChunk
from app.services.qa import organize_citations, select_context_chunks_for_answer
from app.services.reranking import RerankerError, rerank_candidates


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "retrieval_eval_cases.json"


def _chunk(
    *,
    chunk_id: str,
    document_id: int,
    score: float,
    text: str,
    document_name: str = "doc.txt",
    section_title: str | None = None,
    heading_path: tuple[str, ...] | None = None,
    source_locator: str | None = None,
    page_number: int | None = None,
    char_start: int | None = None,
    char_end: int | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=document_id,
        knowledge_base_id=1,
        scope="personal",
        team_id=None,
        document_name=document_name,
        text=text,
        snippet=text,
        source_type="text",
        char_start=char_start,
        char_end=char_end,
        page_number=page_number,
        start_time=None,
        end_time=None,
        section_title=section_title,
        source_locator=source_locator,
        heading_path=heading_path,
        score=score,
    )


def test_rerank_promotes_more_relevant_chunk() -> None:
    candidates = [
        _chunk(
            chunk_id="1:0",
            document_id=1,
            score=0.74,
            text="General project overview without the deployment checklist details.",
        ),
        _chunk(
            chunk_id="2:0",
            document_id=2,
            score=0.68,
            text="Alpha deployment checklist includes preflight checks and rollback steps.",
        ),
    ]

    reranked = rerank_candidates(
        query="alpha deployment checklist",
        candidates=candidates,
        top_k=2,
    )

    assert reranked[0].chunk_id == "2:0"
    assert reranked[0].score >= reranked[1].score


def test_rerank_uses_metadata_hits_to_improve_order() -> None:
    candidates = [
        _chunk(
            chunk_id="1:0",
            document_id=1,
            score=0.72,
            text="This chunk references release workflows in general terms.",
        ),
        _chunk(
            chunk_id="2:0",
            document_id=2,
            score=0.66,
            text="Rollback guidance for the team lives here.",
            section_title="Release Notes",
            heading_path=("Operations", "Release Notes"),
            source_locator="section:Release Notes",
        ),
    ]

    reranked = rerank_candidates(
        query="release notes rollback guidance",
        candidates=candidates,
        top_k=2,
    )

    assert reranked[0].chunk_id == "2:0"


def test_ask_context_selection_limits_single_document_overlap() -> None:
    chunks = [
        _chunk(
            chunk_id="1:0",
            document_id=1,
            score=0.95,
            text="Alpha chunk one explains the first rollout step.",
            char_start=0,
            char_end=80,
            source_locator="chars:0-80",
        ),
        _chunk(
            chunk_id="1:1",
            document_id=1,
            score=0.92,
            text="Alpha chunk two explains the second rollout step.",
            char_start=90,
            char_end=170,
            source_locator="chars:90-170",
        ),
        _chunk(
            chunk_id="1:2",
            document_id=1,
            score=0.91,
            text="Alpha chunk three repeats the second rollout step with minor wording changes.",
            char_start=95,
            char_end=175,
            source_locator="chars:95-175",
        ),
        _chunk(
            chunk_id="2:0",
            document_id=2,
            score=0.88,
            text="Bravo chunk provides an independent supporting citation.",
            char_start=0,
            char_end=70,
            source_locator="chars:0-70",
        ),
    ]

    selected = select_context_chunks_for_answer(chunks)
    selected_ids = [item.chunk_id for item in selected]

    assert selected_ids.count("1:0") == 1
    assert selected_ids.count("1:1") == 1
    assert "1:2" not in selected_ids


def test_citation_organization_preserves_order_and_deduplicates_locator() -> None:
    chunks = [
        _chunk(
            chunk_id="1:0",
            document_id=1,
            score=0.95,
            text="Primary chunk",
            source_locator="section:Runbook",
            section_title="Runbook",
        ),
        _chunk(
            chunk_id="1:1",
            document_id=1,
            score=0.90,
            text="Duplicate locator chunk",
            source_locator="section:Runbook",
            section_title="Runbook",
        ),
        _chunk(
            chunk_id="2:0",
            document_id=2,
            score=0.88,
            text="Secondary citation",
            source_locator="page:2",
            page_number=2,
        ),
    ]

    organized = organize_citations(chunks)

    assert [item.chunk_id for item in organized] == ["1:0", "2:0"]


def test_rerank_falls_back_to_hybrid_order_when_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [
        _chunk(chunk_id="1:0", document_id=1, score=0.91, text="First chunk"),
        _chunk(chunk_id="2:0", document_id=2, score=0.82, text="Second chunk"),
    ]

    monkeypatch.setattr(
        "app.services.reranking.resolve_reranker",
        lambda settings=None: (_ for _ in ()).throw(RerankerError("boom")),
    )

    reranked = rerank_candidates(
        query="first chunk",
        candidates=candidates,
        top_k=2,
    )

    assert [item.chunk_id for item in reranked] == ["1:0", "2:0"]


def test_retrieval_eval_fixture_is_well_formed() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    assert len(payload) >= 6
    assert {item["document_type"] for item in payload} >= {"txt", "md", "pdf"}
    assert all(item["query"] for item in payload)
