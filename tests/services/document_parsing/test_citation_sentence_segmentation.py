from __future__ import annotations

import pytest

from app.services.document_processing import (
    GeneratedChunkPayload,
    build_citation_units_for_chunk,
    split_text_into_sentence_spans,
)


@pytest.mark.parametrize(
    "sentence",
    [
        "RETRIEVAL_MIN_SCORE defaults to 0.15.",
        "Aurora Pro weighs 2.1 kg.",
        "Python 3.12.4 is supported.",
        "The server listens on 127.0.0.1.",
        "Import app.core.config before startup.",
    ],
)
def test_sentence_segmentation_preserves_decimal_and_technical_dots(
    sentence: str,
) -> None:
    spans = split_text_into_sentence_spans(sentence)

    assert [span.text for span in spans] == [sentence]
    assert sentence[spans[0].start_char:spans[0].end_char] == sentence


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "Read config.py. Then restart the service.",
            ["Read config.py.", "Then restart the service."],
        ),
        (
            "The default is 0.15. Low scores are rejected.",
            ["The default is 0.15.", "Low scores are rejected."],
        ),
        (
            'The default is "0.15". Next sentence.',
            ['The default is "0.15".', "Next sentence."],
        ),
        (
            "The default is (0.15). Next sentence.",
            ["The default is (0.15).", "Next sentence."],
        ),
        ("第一条。第二条！第三条？", ["第一条。", "第二条！", "第三条？"]),
    ],
)
def test_sentence_segmentation_keeps_real_boundaries(
    source: str,
    expected: list[str],
) -> None:
    spans = split_text_into_sentence_spans(source)

    assert [span.text for span in spans] == expected
    assert [source[span.start_char:span.end_char] for span in spans] == expected


@pytest.mark.parametrize(
    "fact",
    [
        "Aurora Pro 重量：2.1 kg。",
        "Python calls __init__ during instantiation.",
        "CHUNK_STRATEGY supports fixed and block_aware.",
        "graph_vector_mix handles relation-oriented questions.",
        "docker compose down -v removes volumes.",
    ],
)
def test_citation_units_preserve_cross_domain_technical_facts(fact: str) -> None:
    units = build_citation_units_for_chunk(
        chunk=GeneratedChunkPayload(
            chunk_key="1:0",
            chunk_index=0,
            chunk_text=fact,
            metadata_json='{"source_type":"text","char_start":0}',
        ),
        chunk_metadata={"source_type": "text", "char_start": 0},
        min_chars=1,
        target_chars=120,
        max_chars=200,
        max_sentences=3,
    )

    assert len(units) == 1
    assert units[0].unit_text == fact
    assert (units[0].start_char, units[0].end_char) == (0, len(fact))
