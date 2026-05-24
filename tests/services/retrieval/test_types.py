from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.retrieval import (
    RetrievedEvidence,
    RetrievalMode,
    RetrievalRequest,
    RetrievalResult,
)


def test_retrieval_mode_defines_m1_and_future_modes() -> None:
    assert RetrievalMode.CHUNK_ONLY.value == "chunk_only"
    assert RetrievalMode.OVERVIEW.value == "overview"
    assert RetrievalMode.GRAPH_LOCAL.value == "graph_local"


def test_retrieval_request_validates_required_input() -> None:
    request = RetrievalRequest(
        query=" PureLink retrieval ",
        knowledge_base_id=1,
        user_id=2,
    )

    assert request.query == "PureLink retrieval"
    assert request.mode == RetrievalMode.CHUNK_ONLY
    assert request.top_k == 8

    with pytest.raises(ValidationError):
        RetrievalRequest(query=" ", knowledge_base_id=1, user_id=2)


def test_retrieval_result_serializes_evidence() -> None:
    result = RetrievalResult(
        query="what is purelink",
        mode=RetrievalMode.CHUNK_ONLY,
        evidences=[
            RetrievedEvidence(
                document_id=1,
                chunk_id="1:0",
                citation_unit_id=10,
                text="PureLink is a knowledge base system.",
                source_locator="chars:0-39",
                document_name="intro.txt",
                final_score=0.9,
            )
        ],
        context_text="[S1]\ncontent: PureLink is a knowledge base system.",
    )

    payload = result.model_dump(mode="json")

    assert payload["mode"] == "chunk_only"
    assert payload["evidences"][0]["citation_unit_id"] == 10
    assert payload["evidences"][0]["metadata"] == {}
