from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.services.retrieval.types import RetrievedEvidence


def build_evidences(raw_results: Sequence[Any]) -> list[RetrievedEvidence]:
    return [
        _build_evidence(item, fallback_marker=f"S{index}")
        for index, item in enumerate(raw_results, start=1)
    ]


def _build_evidence(item: Any, *, fallback_marker: str) -> RetrievedEvidence:
    marker = _get_attr(item, "marker") or fallback_marker
    score = _get_attr(item, "score")
    heading_path = _get_attr(item, "heading_path")
    return RetrievedEvidence(
        document_id=int(_get_attr(item, "document_id")),
        chunk_id=_get_attr(item, "chunk_id"),
        citation_unit_id=_get_attr(item, "citation_unit_id"),
        citation_id=_get_attr(item, "citation_id"),
        chunk_db_id=_get_attr(item, "chunk_db_id"),
        text=str(_get_attr(item, "text") or ""),
        source_locator=_get_attr(item, "source_locator"),
        knowledge_base_id=_get_attr(item, "knowledge_base_id"),
        scope=_get_attr(item, "scope"),
        team_id=_get_attr(item, "team_id"),
        document_name=_get_attr(item, "document_name"),
        snippet=_get_attr(item, "snippet"),
        source_type=_get_attr(item, "source_type"),
        char_start=_get_attr(item, "char_start"),
        char_end=_get_attr(item, "char_end"),
        page_number=_get_attr(item, "page_number"),
        start_time=_get_attr(item, "start_time"),
        end_time=_get_attr(item, "end_time"),
        section_title=_get_attr(item, "section_title"),
        heading_path=list(heading_path) if heading_path else None,
        final_score=score,
        metadata={"marker": marker},
    )


def _get_attr(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)
