from __future__ import annotations

from types import SimpleNamespace

from app.services.answer_policy import (
    AnswerPolicyOutcome,
    REASON_EVIDENCE_SUPPORT_REJECTED,
    REASON_FINAL_EVIDENCE_NOT_CITATION_ALIGNED,
    REASON_NO_CITATION_READY_EVIDENCE,
    REASON_SUPPORTED_WITHOUT_FINAL_EVIDENCE,
    decide_answer_policy,
    validate_provider_markers,
)


def _evidence(
    marker: str,
    *,
    citation_unit_id: int | None = 1,
    source_locator: str | None = "section:Facts",
):
    return SimpleNamespace(
        marker=marker,
        citation_unit_id=citation_unit_id,
        source_locator=source_locator,
    )


def test_answer_policy_refuses_when_support_gate_rejects() -> None:
    decision = decide_answer_policy(
        support_answerable=False,
        support_reason="missing_attribute_support",
        final_evidences=[_evidence("S1")],
    )

    assert decision.outcome == AnswerPolicyOutcome.REFUSE
    assert decision.reason == REASON_EVIDENCE_SUPPORT_REJECTED
    assert decision.allow_provider_call is False
    assert decision.citation_required is False
    assert decision.external_knowledge_allowed is False
    assert decision.evidence_markers == ()
    assert decision.unsupported_aspects == ("missing_attribute_support",)


def test_answer_policy_answers_with_citation_ready_final_evidence() -> None:
    decision = decide_answer_policy(
        support_answerable=True,
        support_reason="supported",
        final_evidences=[_evidence("S1"), _evidence("S2", citation_unit_id=2)],
    )

    assert decision.outcome == AnswerPolicyOutcome.ANSWER
    assert decision.allow_provider_call is True
    assert decision.citation_required is True
    assert decision.external_knowledge_allowed is False
    assert decision.evidence_markers == ("S1", "S2")
    assert "Use only the supplied Evidence Units as factual sources." in decision.policy_instructions


def test_answer_policy_refuses_supported_result_without_final_evidence() -> None:
    decision = decide_answer_policy(
        support_answerable=True,
        support_reason="supported",
        final_evidences=[],
    )

    assert decision.outcome == AnswerPolicyOutcome.REFUSE
    assert decision.reason == REASON_SUPPORTED_WITHOUT_FINAL_EVIDENCE
    assert decision.allow_provider_call is False


def test_answer_policy_refuses_when_all_final_evidence_is_non_ready() -> None:
    decision = decide_answer_policy(
        support_answerable=True,
        support_reason="supported",
        final_evidences=[
            _evidence("S1", citation_unit_id=None),
            _evidence("S2", citation_unit_id=2, source_locator=None),
        ],
    )

    assert decision.outcome == AnswerPolicyOutcome.REFUSE
    assert decision.reason == REASON_NO_CITATION_READY_EVIDENCE
    assert decision.allow_provider_call is False
    assert decision.evidence_markers == ()


def test_answer_policy_refuses_mixed_ready_and_non_ready_final_evidence() -> None:
    decision = decide_answer_policy(
        support_answerable=True,
        support_reason="supported",
        final_evidences=[
            _evidence("S1"),
            _evidence("S2", citation_unit_id=None),
        ],
    )

    assert decision.outcome == AnswerPolicyOutcome.REFUSE
    assert decision.reason == REASON_FINAL_EVIDENCE_NOT_CITATION_ALIGNED
    assert decision.allow_provider_call is False
    assert decision.evidence_markers == ()


def test_provider_marker_validation_removes_unknown_and_deduplicates_citations() -> None:
    validation = validate_provider_markers(
        answer_text="First [S2, S99, S2]. Second [1]. Repeat [S2].",
        allowed_markers=("S1", "S2"),
    )

    assert validation.answer_text == "First [S2]. Second [S1]. Repeat [S2]."
    assert validation.used_markers == ("S2", "S1")
    assert validation.unknown_markers_removed == 1


def test_answer_policy_trace_metadata_is_internal_and_deterministic() -> None:
    decision = decide_answer_policy(
        support_answerable=True,
        support_reason="supported",
        final_evidences=[_evidence("S1")],
    )

    assert decision.to_trace_metadata(
        provider_called=True,
        unknown_markers_removed=2,
    ) == {
        "answer_policy_outcome": "answer",
        "answer_policy_reason": "supported",
        "answer_provider_called": True,
        "answer_citation_required": True,
        "answer_external_knowledge_allowed": False,
        "answer_allowed_evidence_count": 1,
        "answer_allowed_markers": ["S1"],
        "answer_unknown_markers_removed": 2,
    }


def test_partial_and_conflict_outcomes_are_reserved_but_not_inferred() -> None:
    decision = decide_answer_policy(
        support_answerable=True,
        support_reason="supported",
        final_evidences=[_evidence("S1"), _evidence("S2", citation_unit_id=2)],
    )

    assert decision.outcome == AnswerPolicyOutcome.ANSWER
    assert decision.unsupported_aspects == ()
    assert decision.conflict_notes == ()
