from __future__ import annotations

from pathlib import Path
import re

from app.services import document_processing
from app.services.document_parsing.block_normalizer import blocks_to_plain_text, normalize_blocks
from app.services.document_parsing.types import DocumentBlock, DocumentBlockType, ParsedDocument


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_PATTERN = re.compile(r"^```([A-Za-z0-9_-]+)?\s*$")


class MarkdownParser:
    parser_name = "markdown"

    def supports(self, *, filename: str, mime_type: str | None = None) -> bool:
        return Path(filename).suffix.lower() == ".md"

    def parse(
        self,
        file_path: Path,
        *,
        filename: str,
        mime_type: str | None = None,
    ) -> ParsedDocument:
        decoded_text, encoding = document_processing.read_text_file_with_fallback(file_path)
        blocks = _parse_markdown_blocks(decoded_text)
        normalized_blocks = normalize_blocks(blocks)
        return ParsedDocument(
            text=blocks_to_plain_text(normalized_blocks),
            blocks=normalized_blocks,
            metadata={
                "parser": self.parser_name,
                "source_type": "markdown",
                "extractor": "markdown",
                "encoding": encoding,
                "original_filename": filename,
            },
        )


def _parse_markdown_blocks(text: str) -> list[DocumentBlock]:
    blocks: list[DocumentBlock] = []
    paragraph_lines: list[str] = []
    table_lines: list[str] = []
    code_lines: list[str] = []
    in_code = False
    code_language: str | None = None
    current_heading: str | None = None

    def append_block(kind: DocumentBlockType, value: str, **metadata) -> None:
        if not value.strip():
            return
        blocks.append(
            DocumentBlock(
                block_type=kind,
                text=value.strip(),
                order_index=len(blocks),
                heading_level=metadata.pop("heading_level", None),
                metadata={
                    "source_type": "markdown",
                    **({"section_title": current_heading} if current_heading else {}),
                    **metadata,
                },
            )
        )

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            append_block(
                DocumentBlockType.TEXT,
                " ".join(
                    document_processing.normalize_markdown_inline_text(line)
                    for line in paragraph_lines
                ),
            )
            paragraph_lines = []

    def flush_table() -> None:
        nonlocal table_lines
        if table_lines:
            append_block(
                DocumentBlockType.TABLE,
                "\n".join(table_lines),
                block_type=DocumentBlockType.TABLE.value,
            )
            table_lines = []

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        fence_match = FENCE_PATTERN.match(line.strip())
        if fence_match:
            if in_code:
                append_block(
                    DocumentBlockType.CODE,
                    "\n".join(code_lines),
                    block_type=DocumentBlockType.CODE.value,
                    language=code_language,
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

        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_table()
            continue

        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match is not None:
            flush_paragraph()
            flush_table()
            current_heading = document_processing.normalize_markdown_inline_text(heading_match.group(2))
            append_block(
                DocumentBlockType.HEADING,
                current_heading,
                heading_level=len(heading_match.group(1)),
            )
            continue

        if _looks_like_table_row(stripped):
            flush_paragraph()
            table_lines.append(stripped)
            continue

        flush_table()
        paragraph_lines.append(stripped)

    if in_code:
        append_block(
            DocumentBlockType.CODE,
            "\n".join(code_lines),
            block_type=DocumentBlockType.CODE.value,
            language=code_language,
        )
    flush_paragraph()
    flush_table()
    return blocks


def _looks_like_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|") and line.count("|") >= 2
