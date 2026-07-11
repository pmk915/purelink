from __future__ import annotations

from app.models.enums import DocumentBlockType
from app.services.document_parsing.parsers.text_parser import TextParser
from app.services.document_parsing.structured_text import (
    detect_markdown_like_structure,
    parse_structured_text_blocks,
    structured_blocks_to_text,
)


def test_detect_markdown_like_structure_requires_multiple_headings_and_body() -> None:
    assert detect_markdown_like_structure(
        "Intro\n\n### 一、基本设定\n乌萨奇是角色。\n\n### 二、外貌\n耳朵很长。"
    )
    assert not detect_markdown_like_structure("Just a plain text note without headings.")
    assert not detect_markdown_like_structure("# Only one heading\n\nBody text.")
    assert not detect_markdown_like_structure("```bash\n# comment\n## another comment\n```\nBody")
    assert not detect_markdown_like_structure("#!/usr/bin/env bash\n\n##! /bin/sh\n\necho hi")


def test_parse_structured_text_blocks_preserves_text_source_type_and_line_roles() -> None:
    blocks = parse_structured_text_blocks(
        "### 一、基本设定\n"
        "乌萨奇是吉伊卡哇作品中的角色。\n"
        "别名：兔兔\n"
        "- 喜欢吃东西\n\n"
        "### 二、外貌\n"
        "形似动物：兔子\n",
        source_type="text",
    )

    assert [block.block_type for block in blocks] == [
        DocumentBlockType.HEADING,
        DocumentBlockType.TEXT,
        DocumentBlockType.TEXT,
        DocumentBlockType.TEXT,
        DocumentBlockType.HEADING,
        DocumentBlockType.TEXT,
    ]
    assert blocks[0].heading_level == 3
    assert blocks[0].metadata["source_type"] == "text"
    assert blocks[2].metadata["line_role"] == "field"
    assert blocks[3].metadata["line_role"] == "list_item"
    assert blocks[-1].metadata["section_title"] == "二、外貌"
    assert blocks[-1].metadata["heading_path"] == ["二、外貌"]

    plain_text = structured_blocks_to_text(blocks)
    for block in blocks:
        assert plain_text[block.metadata["char_start"]:block.metadata["char_end"]] == block.text


def test_text_parser_uses_structured_blocks_for_markdown_like_txt(tmp_path) -> None:
    source = tmp_path / "usagi.txt"
    source.write_text(
        "### 一、基本设定\n"
        "乌萨奇是角色。\n"
        "生日：2019年1月22日\n\n"
        "### 二、关系\n"
        "吉伊卡哇：朋友\n",
        encoding="utf-8",
    )

    parsed = TextParser().parse(source, filename="usagi.txt")

    assert parsed.metadata["source_type"] == "text"
    assert parsed.metadata["extractor"] == "text:structured"
    assert parsed.metadata["markdown_like"] is True
    assert [block.block_type for block in parsed.blocks].count(DocumentBlockType.HEADING) == 2
    assert any(block.metadata.get("line_role") == "field" for block in parsed.blocks)
