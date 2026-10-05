from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services.document_embedding import RetrievedChunk
from app.services.evidence_support import evaluate_evidence_support
from app.services.qa import build_query_evidence_profile, select_evidence_units
from app.services.query_analysis import analyze_evidence_query, evidence_text_has_attribute
from app.services.retrieval.citation_builder import build_evidences
from app.services.retrieval.types import RetrievedEvidence


def _chunk(text, *, document_id=1, score=0.9, section_title=None):
    return RetrievedChunk(
        chunk_id=f"{document_id}:0", document_id=document_id, knowledge_base_id=1,
        scope="personal", team_id=None, document_name=f"manual-{document_id}.pdf",
        text=text, snippet=text, source_type="pdf", char_start=0, char_end=len(text),
        page_number=2, start_time=None, end_time=None, section_title=section_title,
        source_locator="page:2", heading_path=None, score=score,
    )


def _units(chunk, *texts):
    return [SimpleNamespace(
        id=chunk.document_id * 100 + index, chunk_id=index, unit_text=text,
        start_char=chunk.text.index(text), end_char=chunk.text.index(text) + len(text),
        metadata_json=json.dumps({"source_type": "pdf", "page_number": 2, "source_locator": "page:2"}),
    ) for index, text in enumerate(texts, 1)]


def _select(question, chunks, units):
    return select_evidence_units(
        question=question, retrieved_chunks=chunks, chunk_units=units, max_evidence_units=8,
    )


def test_generic_selection_prefers_direct_fact_over_heading_and_sibling_value():
    texts = ["Harbor Deployment Profiles", "Harbor standard profile memory: 512 MiB.",
             "Harbor compact profile memory: 128 MiB."]
    chunk = _chunk("\n".join(texts), section_title="Harbor compact profile memory")
    selected = _select("How much memory does the compact profile reserve for Harbor?", [chunk],
                       {chunk.chunk_id: _units(chunk, *texts)})
    assert [unit.text for unit in selected] == [texts[2]]
    # The third unit is considered before a per-chunk quota can discard it.
    assert selected[0].citation_unit_id == 103


def test_generic_selection_keeps_independent_facets_and_removes_repeated_support():
    texts = ["Summit can preserve sessions in a journal.",
             "Summit can encrypt backups with a local key."]
    chunk = _chunk("\n".join(texts))
    units = _units(chunk, *texts)
    duplicate = SimpleNamespace(**{**vars(units[0]), "id": 999})
    selected = _select("How does Summit preserve sessions and encrypt backups?", [chunk],
                       {chunk.chunk_id: [*units, duplicate]})
    assert {unit.text for unit in selected} == set(texts)
    assert len(selected) == 2
    assert [unit.marker for unit in selected] == ["S1", "S2"]
    for unit in selected:
        source = next(original for original in units if original.id == unit.citation_unit_id)
        assert (unit.text, unit.char_start, unit.char_end) == (source.unit_text, source.start_char, source.end_char)
        assert unit.page_number == 2 and unit.source_locator == "page:2"
    assert all(evidence.page_number == 2 and evidence.source_locator == "page:2" for evidence in build_evidences(selected))


def test_generic_selection_discards_cross_document_and_cross_section_noise():
    fact = "Harbor retains audit records for 21 days."
    unrelated = "Meadow retains audit records for 80 days."
    sibling = "Harbor starts workers on demand."
    relevant_chunk = _chunk(fact + "\n" + sibling)
    noise_chunk = _chunk(unrelated, document_id=2, score=0.6)
    selected = _select("How many days does Harbor retain audit records?", [relevant_chunk, noise_chunk], {
        relevant_chunk.chunk_id: _units(relevant_chunk, fact, sibling),
        noise_chunk.chunk_id: _units(noise_chunk, unrelated),
    })
    assert [unit.text for unit in selected] == [fact]


def test_generic_selection_does_not_choose_question_shaped_label_over_fact():
    texts = ["Summit Recovery", "Summit Recovery says to restore the journal and restart the worker."]
    chunk = _chunk("\n".join(texts))
    selected = _select("What steps does Summit Recovery specify?", [chunk], {chunk.chunk_id: _units(chunk, *texts)})
    assert [unit.text for unit in selected] == [texts[1]]


def test_low_lexical_signal_keeps_paraphrased_multi_unit_support():
    texts = ["Redis triggers tasks.", "ProcessingJob persists task state."]
    chunk = _chunk("\n".join(texts))
    selected = _select("How is task durability ensured during service interruptions?", [chunk],
                       {chunk.chunk_id: _units(chunk, *texts)})
    assert {unit.text for unit in selected} == set(texts)


def test_exact_technical_selection_keeps_identifier_and_rejects_near_match():
    texts = ["CACHE_LIMIT defaults to 8.", "CACHE_LIMIT_EXTRA defaults to 64."]
    chunk = _chunk("\n".join(texts))
    selected = _select("What is the default value of CACHE_LIMIT?", [chunk], {chunk.chunk_id: _units(chunk, *texts)})
    assert [unit.text for unit in selected] == [texts[0]]


def test_no_answer_attribute_expectations_are_not_replaced_by_generic_evidence():
    text = "Summit runs locally and preserves a journal."
    chunk = _chunk(text)
    question = "What is the release date of Summit?"
    selected = _select(question, [chunk], {chunk.chunk_id: _units(chunk, text)})
    assert selected == []
    decision = evaluate_evidence_support(query=question, evidence_units=[], profile=build_query_evidence_profile(question))
    assert decision.answerable is False


@pytest.mark.parametrize("question", [
    "Who maintains the current Harbor runtime?", "Who owns Harbor?", "Who maintains Harbor?",
])
def test_responsibility_binding_uses_named_target_and_shared_passive_alias(question):
    analysis = analyze_evidence_query(question)
    assert analysis.entities == ("Harbor",)
    assert analysis.requested_attributes == ("responsibility",)
    fact = "Harbor is maintained by Dana Ives."
    assert evidence_text_has_attribute(fact, "responsibility")
    chunk = _chunk(fact)
    selected = _select(question, [chunk], {chunk.chunk_id: _units(chunk, fact)})
    assert [unit.text for unit in selected] == [fact]
    decision = evaluate_evidence_support(
        query=question, evidence_units=build_evidences(selected), profile=build_query_evidence_profile(question),
    )
    assert decision.answerable is True
    assert decision.signals["requested_attribute_coverage"] is True


def test_responsibility_gate_still_rejects_wrong_entity_and_missing_attribute():
    question = "Who maintains Harbor?"
    for text in ("Meadow is maintained by Dana Ives.", "Harbor has a local journal."):
        chunk = _chunk(text)
        assert _select(question, [chunk], {chunk.chunk_id: _units(chunk, text)}) == []
        decision = evaluate_evidence_support(
            query=question, evidence_units=[RetrievedEvidence(document_id=1, document_name="manual.pdf", chunk_id="1:0", text=text, final_score=0.99)],
            profile=build_query_evidence_profile(question),
        )
        assert decision.answerable is False


def test_generic_selection_uses_existing_maximum_for_many_independent_facets():
    texts = ["Harbor authentication uses local tokens.", "Harbor backups use a journal.", "Harbor auditing retains records."]
    chunk = _chunk("\n".join(texts))
    selected = select_evidence_units(
        question="How does Harbor handle authentication, backups and auditing?", retrieved_chunks=[chunk],
        chunk_units={chunk.chunk_id: _units(chunk, *texts)}, max_evidence_units=2,
    )
    assert len(selected) == 2 and len({unit.text for unit in selected}) == 2
