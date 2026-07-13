from __future__ import annotations

import re

from app.models.enums import DocumentBlockType
from app.services.document_parsing.block_normalizer import (
    assign_block_char_ranges,
    blocks_to_plain_text,
    normalize_blocks,
)
from app.services.document_parsing.types import DocumentBlock


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(\S.*)$")
FENCE_PATTERN = re.compile(r"^```([A-Za-z0-9_-]+)?\s*$")
LIST_MARKER_PATTERN = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[([^\]]*)\]\([^)]+\)")
MARKDOWN_STRONG_PATTERN = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
MARKDOWN_STRIKE_PATTERN = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
MARKDOWN_ITALIC_ASTERISK_PATTERN = re.compile(
    r"(?<!\*)\*(?!\*)(?=\S)(.+?)(?<=\S)(?<!\*)\*(?!\*)"
)
MARKDOWN_ITALIC_UNDERSCORE_PATTERN = re.compile(
    r"(?<![\w_])_(?!_)(?=\S)(.+?)(?<=\S)(?<!_)_(?![\w_])"
)
FIELD_LIKE_PATTERN = re.compile(r"^[^：:\n]{1,32}[：:]\s*\S+")


def detect_markdown_like_structure(text: str) -> bool:
    lines = _iter_logical_lines(text)
    candidates: list[tuple[int, str]] = []
    in_code = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        fence_match = FENCE_PATTERN.match(stripped)
        if fence_match:
            in_code = not in_code
            continue
        if in_code:
            continue
        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match is None:
            continue
        heading_text = heading_match.group(2).strip()
        if _looks_like_code_comment_heading(stripped, heading_text):
            continue
        candidates.append((index, heading_text))

    if len(candidates) < 2:
        return False

    non_empty_count = sum(1 for line in lines if line.strip())
    if non_empty_count and len(candidates) / non_empty_count > 0.5:
        return False

    first_heading_index = candidates[0][0]
    if _has_body_text(lines[:first_heading_index]):
        return True

    for (left_index, _), (right_index, _) in zip(candidates, candidates[1:]):
        if _has_body_text(lines[left_index + 1:right_index]):
            return True
    return _has_body_text(lines[candidates[-1][0] + 1:])


def parse_structured_text_blocks(
    text: str,
    *,
    source_type: str,
) -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    paragraph_lines: list[str] = []
    table_lines: list[str] = []
    code_lines: list[str] = []
    in_code = False
    code_language: str | None = None
    heading_stack: list[tuple[int, str]] = []

    def current_section_metadata() -> dict[str, object]:
        heading_path = [text for _, text in heading_stack]
        if not heading_path:
            return {"source_type": source_type}
        return {
            "source_type": source_type,
            "section_title": heading_path[-1],
            "heading_path": list(heading_path),
        }

    def append_block(
        kind: DocumentBlockType,
        value: str,
        *,
        heading_level: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        normalized = value.strip()
        if not normalized:
            return
        blocks.append(
            DocumentBlock(
                block_type=kind,
                text=normalized,
                order_index=len(blocks),
                heading_level=heading_level,
                metadata={
                    **current_section_metadata(),
                    **(metadata or {}),
                },
            )
        )

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            append_block(
                DocumentBlockType.TEXT,
                " ".join(_normalize_markdown_inline_text(line) for line in paragraph_lines),
            )
            paragraph_lines = []

    def flush_table() -> None:
        nonlocal table_lines
        if table_lines:
            append_block(
                DocumentBlockType.TABLE,
                "\n".join(table_lines),
                metadata={"block_type": DocumentBlockType.TABLE.value},
            )
            table_lines = []

    for raw_line in _iter_logical_lines(text):
        line = raw_line.rstrip()
        stripped = line.strip()
        fence_match = FENCE_PATTERN.match(stripped)
        if fence_match:
            if in_code:
                append_block(
                    DocumentBlockType.CODE,
                    "\n".join(code_lines),
                    metadata={
                        "block_type": DocumentBlockType.CODE.value,
                        **({"language": code_language} if code_language else {}),
                    },
                )
                code_lines = []
                code_language = None
                in_code = False
            else:
                flush_paragraph()
                flush_table()
                in_code = True
                code_language = fence_match.group(1)
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            flush_table()
            continue

        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match is not None:
            flush_paragraph()
            flush_table()
            heading_level = len(heading_match.group(1))
            heading_text = _normalize_markdown_inline_text(heading_match.group(2))
            _update_heading_stack(heading_stack, heading_text, heading_level)
            append_block(
                DocumentBlockType.HEADING,
                heading_text,
                heading_level=heading_level,
            )
            continue

        if _looks_like_table_row(stripped):
            flush_paragraph()
            table_lines.append(stripped)
            continue

        flush_table()
        normalized_line = _normalize_markdown_inline_text(stripped)
        if _is_list_item(stripped):
            flush_paragraph()
            append_block(
                DocumentBlockType.TEXT,
                normalized_line,
                metadata={"line_role": _line_role_for_text(normalized_line, default="list_item")},
            )
            continue
        if _is_field_like(normalized_line):
            flush_paragraph()
            append_block(
                DocumentBlockType.TEXT,
                normalized_line,
                metadata={"line_role": "field"},
            )
            continue
        paragraph_lines.append(stripped)

    if in_code:
        append_block(
            DocumentBlockType.CODE,
            "\n".join(code_lines),
            metadata={
                "block_type": DocumentBlockType.CODE.value,
                **({"language": code_language} if code_language else {}),
            },
        )
    flush_paragraph()
    flush_table()
    return assign_block_char_ranges(normalize_blocks(blocks))


def structured_blocks_to_text(blocks: list[DocumentBlock]) -> str:
    return blocks_to_plain_text(blocks)


def _iter_logical_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _has_body_text(lines: list[str]) -> bool:
    in_code = False
    for line in lines:
        stripped = line.strip()
        fence_match = FENCE_PATTERN.match(stripped)
        if fence_match:
            in_code = not in_code
            continue
        if in_code or not stripped:
            continue
        if HEADING_PATTERN.match(stripped) is not None:
            continue
        return True
    return False


def _looks_like_code_comment_heading(line: str, heading_text: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("#!") or stripped.startswith("##!"):
        return True
    lowered = heading_text.lower()
    return lowered.startswith(("include ", "define ", "pragma ", "!/"))


def _normalize_markdown_inline_text(text: str) -> str:
    normalized = text.strip()
    if normalized.startswith(">"):
        normalized = normalized.lstrip(">").strip()
    normalized = LIST_MARKER_PATTERN.sub("", normalized)
    normalized = MARKDOWN_LINK_PATTERN.sub(r"\1", normalized)
    normalized = normalized.replace("`", "")
    normalized = MARKDOWN_STRONG_PATTERN.sub(r"\1", normalized)
    normalized = MARKDOWN_STRIKE_PATTERN.sub(r"\1", normalized)
    normalized = MARKDOWN_ITALIC_ASTERISK_PATTERN.sub(r"\1", normalized)
    normalized = MARKDOWN_ITALIC_UNDERSCORE_PATTERN.sub(r"\1", normalized)
    return normalized.strip()


def _looks_like_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|") and line.count("|") >= 2


def _is_list_item(line: str) -> bool:
    return LIST_MARKER_PATTERN.match(line) is not None


def _is_field_like(text: str) -> bool:
    return FIELD_LIKE_PATTERN.match(text.strip()) is not None


def _line_role_for_text(text: str, *, default: str) -> str:
    return "field" if _is_field_like(text) else default


def _update_heading_stack(
    heading_stack: list[tuple[int, str]],
    heading: str,
    heading_level: int | None,
) -> None:
    level = max(1, min(int(heading_level or 1), 6))
    while heading_stack and heading_stack[-1][0] >= level:
        heading_stack.pop()
    heading_stack.append((level, heading))
