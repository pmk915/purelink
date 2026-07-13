from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum
import re
from typing import Any


class AnswerPolicyOutcome(str, Enum):
    ANSWER = "answer"
    REFUSE = "refuse"
    ANSWER_WITH_LIMITATIONS = "answer_with_limitations"
    PRESENT_CONFLICT = "present_conflict"


REASON_SUPPORTED = "supported"
REASON_EVIDENCE_SUPPORT_REJECTED = "evidence_support_rejected"
REASON_UNRELIABLE_RETRIEVAL_CONTEXT = "unreliable_retrieval_context"
REASON_SUPPORTED_WITHOUT_FINAL_EVIDENCE = "supported_without_final_evidence"
REASON_NO_CITATION_READY_EVIDENCE = "no_citation_ready_evidence"
REASON_FINAL_EVIDENCE_NOT_CITATION_ALIGNED = "final_evidence_not_citation_aligned"
REASON_NO_VALID_CITATION_MARKERS = "no_valid_citation_markers"
REASON_NO_VALID_CITATIONS = "no_valid_citations"

POLICY_INSTRUCTIONS = (
    "Use only the supplied Evidence Units as factual sources.",
    "Do not use model memory or external knowledge to add facts.",
    "Do not invent defaults, relationships, causes, dates, states, or configuration values.",
    "Every factual claim must be supported by at least one allowed evidence marker.",
    "Do not cite markers that are not in the allowed marker list.",
    "Do not treat retrieval scores, router reasons, or support scores as answer facts.",
    "Do not complete missing facts when the evidence is insufficient.",
    "Answer in the language used by the current question.",
    "Answer directly without repeating the full question.",
)

_CITATION_MARKER_PATTERN = re.compile(
    r"\[((?:\s*[Ss]?\d+\s*(?:,\s*[Ss]?\d+\s*)*))\]"
)


@dataclass(frozen=True, slots=True)
class AnswerPolicyDecision:
    outcome: AnswerPolicyOutcome
    reason: str
    allow_provider_call: bool
    citation_required: bool
    external_knowledge_allowed: bool
    evidence_markers: tuple[str, ...]
    policy_instructions: tuple[str, ...] = POLICY_INSTRUCTIONS
    unsupported_aspects: tuple[str, ...] = ()
    conflict_notes: tuple[str, ...] = ()

    def to_trace_metadata(
        self,
        *,
        provider_called: bool,
        unknown_markers_removed: int = 0,
    ) -> dict[str, object]:
        return {
            "answer_policy_outcome": self.outcome.value,
            "answer_policy_reason": self.reason,
            "answer_provider_called": provider_called,
            "answer_citation_required": self.citation_required,
            "answer_external_knowledge_allowed": self.external_knowledge_allowed,
            "answer_allowed_evidence_count": len(self.evidence_markers),
            "answer_allowed_markers": list(self.evidence_markers),
            "answer_unknown_markers_removed": unknown_markers_removed,
        }


@dataclass(frozen=True, slots=True)
class MarkerValidationResult:
    answer_text: str
    used_markers: tuple[str, ...]
    unknown_markers_removed: int


def decide_answer_policy(
    *,
    support_answerable: bool,
    support_reason: str,
    final_evidences: Sequence[Any],
    retrieval_context_reliable: bool = True,
) -> AnswerPolicyDecision:
    evidences = tuple(final_evidences)
    if not support_answerable:
        return _refusal_decision(
            reason=REASON_EVIDENCE_SUPPORT_REJECTED,
            unsupported_aspects=(support_reason,),
        )
    if not evidences:
        return _refusal_decision(reason=REASON_SUPPORTED_WITHOUT_FINAL_EVIDENCE)
    if not retrieval_context_reliable:
        return _refusal_decision(reason=REASON_UNRELIABLE_RETRIEVAL_CONTEXT)

    ready_markers = tuple(
        marker
        for evidence in evidences
        if _is_citation_ready(evidence)
        if (marker := _evidence_marker(evidence)) is not None
    )
    if not ready_markers:
        return _refusal_decision(reason=REASON_NO_CITATION_READY_EVIDENCE)
    if len(ready_markers) != len(evidences):
        return _refusal_decision(reason=REASON_FINAL_EVIDENCE_NOT_CITATION_ALIGNED)

    return AnswerPolicyDecision(
        outcome=AnswerPolicyOutcome.ANSWER,
        reason=REASON_SUPPORTED,
        allow_provider_call=True,
        citation_required=True,
        external_knowledge_allowed=False,
        evidence_markers=_deduplicate_markers(ready_markers),
    )


def refuse_answer_policy(
    decision: AnswerPolicyDecision,
    *,
    reason: str,
) -> AnswerPolicyDecision:
    return replace(
        decision,
        outcome=AnswerPolicyOutcome.REFUSE,
        reason=reason,
        allow_provider_call=False,
        citation_required=False,
    )


def validate_provider_markers(
    *,
    answer_text: str,
    allowed_markers: Sequence[str],
) -> MarkerValidationResult:
    allowed = set(_deduplicate_markers(tuple(allowed_markers)))
    used_markers: list[str] = []
    seen_used: set[str] = set()
    unknown_markers_removed = 0

    def _replace_markers(match: re.Match[str]) -> str:
        nonlocal unknown_markers_removed
        normalized_tokens: list[str] = []
        seen_in_group: set[str] = set()
        for raw_token in match.group(1).split(","):
            marker = normalize_citation_marker(raw_token)
            if marker is None:
                continue
            if marker not in allowed:
                unknown_markers_removed += 1
                continue
            if marker not in seen_used:
                used_markers.append(marker)
                seen_used.add(marker)
            if marker in seen_in_group:
                continue
            normalized_tokens.append(f"[{marker}]")
            seen_in_group.add(marker)
        return "".join(normalized_tokens)

    normalized_answer = _CITATION_MARKER_PATTERN.sub(_replace_markers, answer_text)
    return MarkerValidationResult(
        answer_text=normalized_answer,
        used_markers=tuple(used_markers),
        unknown_markers_removed=unknown_markers_removed,
    )


def extract_citation_markers(answer_text: str) -> tuple[str, ...]:
    markers: list[str] = []
    seen: set[str] = set()
    for match in _CITATION_MARKER_PATTERN.finditer(answer_text):
        for raw_token in match.group(1).split(","):
            marker = normalize_citation_marker(raw_token)
            if marker is None or marker in seen:
                continue
            markers.append(marker)
            seen.add(marker)
    return tuple(markers)


def normalize_citation_marker(value: str) -> str | None:
    digits = re.sub(r"[^0-9]", "", value)
    if not digits:
        return None
    return f"S{int(digits)}"


def _refusal_decision(
    *,
    reason: str,
    unsupported_aspects: tuple[str, ...] = (),
) -> AnswerPolicyDecision:
    return AnswerPolicyDecision(
        outcome=AnswerPolicyOutcome.REFUSE,
        reason=reason,
        allow_provider_call=False,
        citation_required=False,
        external_knowledge_allowed=False,
        evidence_markers=(),
        unsupported_aspects=unsupported_aspects,
    )


def _is_citation_ready(evidence: Any) -> bool:
    return (
        getattr(evidence, "citation_unit_id", None) is not None
        and bool(getattr(evidence, "source_locator", None))
    )


def _evidence_marker(evidence: Any) -> str | None:
    marker = getattr(evidence, "marker", None)
    if marker is None:
        metadata = getattr(evidence, "metadata", None)
        if isinstance(metadata, dict):
            marker = metadata.get("marker")
    if not isinstance(marker, str):
        return None
    normalized = normalize_citation_marker(marker)
    return normalized


def _deduplicate_markers(markers: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(markers))


__all__ = [
    "AnswerPolicyDecision",
    "AnswerPolicyOutcome",
    "MarkerValidationResult",
    "POLICY_INSTRUCTIONS",
    "REASON_EVIDENCE_SUPPORT_REJECTED",
    "REASON_FINAL_EVIDENCE_NOT_CITATION_ALIGNED",
    "REASON_NO_CITATION_READY_EVIDENCE",
    "REASON_NO_VALID_CITATION_MARKERS",
    "REASON_NO_VALID_CITATIONS",
    "REASON_SUPPORTED_WITHOUT_FINAL_EVIDENCE",
    "decide_answer_policy",
    "extract_citation_markers",
    "refuse_answer_policy",
    "validate_provider_markers",
]
