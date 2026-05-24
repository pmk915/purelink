from __future__ import annotations

from app.services.retrieval.types import RetrievedEvidence


def build_context(evidences: list[RetrievedEvidence]) -> str:
    context_lines: list[str] = []
    for index, evidence in enumerate(evidences, start=1):
        marker = str(evidence.metadata.get("marker") or f"S{index}")
        locator_parts = []
        if evidence.document_name:
            locator_parts.append(f"document_name: {evidence.document_name}")
        if evidence.source_type:
            locator_parts.append(f"source_type: {evidence.source_type}")
        if evidence.page_number is not None:
            locator_parts.append(f"page_number: {evidence.page_number}")
        if evidence.start_time is not None and evidence.end_time is not None:
            locator_parts.append(
                f"time_range: {evidence.start_time:.2f}-{evidence.end_time:.2f}"
            )
        if evidence.section_title:
            locator_parts.append(f"section_title: {evidence.section_title}")
        if evidence.source_locator:
            locator_parts.append(f"source_locator: {evidence.source_locator}")

        context_lines.append(f"[{marker}]")
        context_lines.extend(locator_parts)
        context_lines.append(f"content: {evidence.text}")
        context_lines.append("")

    return "\n".join(context_lines).strip() if context_lines else "[no evidence]"
