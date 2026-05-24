from __future__ import annotations

from app.services.retrieval.context_builder import build_context
from app.services.retrieval.types import RetrievedEvidence


def test_build_context_renders_stable_source_markers() -> None:
    context = build_context(
        [
            RetrievedEvidence(
                document_id=1,
                chunk_id="1:0",
                text="First evidence.",
                document_name="alpha.txt",
                source_type="text",
                source_locator="chars:0-15",
                section_title="Overview",
                metadata={"marker": "S1"},
            ),
            RetrievedEvidence(
                document_id=2,
                chunk_id="2:0",
                text="Second evidence.",
                document_name="bravo.txt",
            ),
        ]
    )

    assert "[S1]" in context
    assert "[S2]" in context
    assert "document_name: alpha.txt" in context
    assert "source_locator: chars:0-15" in context
    assert "content: Second evidence." in context


def test_build_context_handles_empty_evidence_list() -> None:
    assert build_context([]) == "[no evidence]"
