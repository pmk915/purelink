from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.services.retrieval.types import RetrievedEvidence

READINESS_READY = "ready"
READINESS_MISSING_CITATION_UNIT_ID = "missing_citation_unit_id"
READINESS_MISSING_SOURCE_LOCATOR = "missing_source_locator"
READINESS_MISSING_BOTH = "missing_both"
READINESS_CHUNK_FALLBACK_WITHOUT_LOCATOR = "chunk_fallback_without_locator"


def build_evidences(raw_results: Sequence[Any]) -> list[RetrievedEvidence]:
    evidences = [
        _build_evidence(item, fallback_marker=f"S{index}")
        for index, item in enumerate(raw_results, start=1)
    ]
    return _deduplicate_evidences(evidences)


def citation_readiness(evidence: RetrievedEvidence) -> tuple[bool, str]:
    has_unit_id = evidence.citation_unit_id is not None
    has_locator = bool(evidence.source_locator)
    if has_unit_id and has_locator:
        return True, READINESS_READY
    if has_unit_id:
        return False, READINESS_MISSING_SOURCE_LOCATOR
    if has_locator:
        return False, READINESS_MISSING_CITATION_UNIT_ID
    if evidence.chunk_db_id is not None:
        return False, READINESS_CHUNK_FALLBACK_WITHOUT_LOCATOR
    return False, READINESS_MISSING_BOTH


def summarize_citation_readiness(
    evidences: Sequence[RetrievedEvidence],
) -> dict[str, object]:
    ready_count = 0
    missing_reasons: dict[str, int] = {}
    for evidence in evidences:
        ready, reason = citation_readiness(evidence)
        if ready:
            ready_count += 1
            continue
        missing_reasons[reason] = missing_reasons.get(reason, 0) + 1
    return {
        "citation_ready_count": ready_count,
        "citation_missing_count": len(evidences) - ready_count,
        "citation_missing_reasons": missing_reasons,
    }


def _build_evidence(item: Any, *, fallback_marker: str) -> RetrievedEvidence:
    marker = _get_attr(item, "marker") or fallback_marker
    score = _get_attr(item, "score")
    heading_path = _get_attr(item, "heading_path")
    selection_metadata = {
        key: value
        for key, value in {
            "attribute_match": _get_attr(item, "attribute_match"),
            "identifier_match": _get_attr(item, "identifier_match"),
            "entity_match": bool(
                _get_attr(item, "entity_exact_match")
                or _get_attr(item, "entity_context_match")
            ),
            "direct_support": _get_attr(item, "direct_support"),
            "coverage_gain": _get_attr(item, "coverage_gain"),
            "rejection_reason": _get_attr(item, "rejection_reason"),
        }.items()
        if value is not None
    }
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
        metadata={"marker": marker, **selection_metadata},
    )


def _get_attr(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _deduplicate_evidences(
    evidences: list[RetrievedEvidence],
) -> list[RetrievedEvidence]:
    deduplicated: list[RetrievedEvidence] = []
    index_by_key: dict[tuple[int, str, str], int] = {}
    for evidence in evidences:
        key = (
            evidence.document_id,
            str(evidence.chunk_id),
            " ".join(evidence.text.split()).casefold(),
        )
        existing_index = index_by_key.get(key)
        if existing_index is None:
            index_by_key[key] = len(deduplicated)
            deduplicated.append(evidence)
            continue
        existing = deduplicated[existing_index]
        if _provenance_rank(evidence) <= _provenance_rank(existing):
            continue
        marker = existing.metadata.get("marker")
        replacement_metadata = dict(evidence.metadata)
        if marker:
            replacement_metadata["marker"] = marker
        deduplicated[existing_index] = evidence.model_copy(
            update={"metadata": replacement_metadata}
        )
    return deduplicated


def _provenance_rank(evidence: RetrievedEvidence) -> tuple[int, int, int]:
    ready, _ = citation_readiness(evidence)
    return (
        int(ready),
        int(evidence.citation_unit_id is not None),
        int(bool(evidence.source_locator)),
    )
