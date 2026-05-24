from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path

from app.models.document import Document
from app.models.enums import KnowledgeBaseScope
from app.services.document_parsing import get_parser
from app.services.document_parsing.block_normalizer import blocks_to_text


SUPPORTED_PARSE_SUFFIXES = {
    ".txt": "plain_text",
    ".md": "markdown",
    ".docx": "minimal_docx_text",
    ".pdf": "pdf_text",
}

logger = logging.getLogger("purelink.documents")


class DocumentParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedDocumentResult:
    parsed_path: str
    parser: str
    extracted_char_count: int


def resolve_parsed_root(parsed_dir: str | Path, *, base_dir: Path) -> Path:
    parsed_root = Path(parsed_dir)
    if not parsed_root.is_absolute():
        parsed_root = base_dir / parsed_root
    return parsed_root


def parse_document_to_local_result(
    *,
    document: Document,
    upload_root: Path,
    parsed_root: Path,
    scope: KnowledgeBaseScope,
    team_id: int | None = None,
) -> ParsedDocumentResult:
    source_path = upload_root / document.storage_path
    logger.info(
        "parse start document_id=%s knowledge_base_id=%s scope=%s team_id=%s source_path=%s",
        document.id,
        document.knowledge_base_id,
        scope.value,
        team_id,
        source_path,
    )
    if not source_path.exists():
        logger.error(
            "parse source missing document_id=%s source_path=%s",
            document.id,
            source_path,
        )
        raise DocumentParseError("Document source file does not exist.")

    logger.info(
        "parse source located document_id=%s source_path=%s size_bytes=%s",
        document.id,
        source_path,
        source_path.stat().st_size,
    )

    suffix = Path(document.original_filename).suffix.lower()
    try:
        parser = get_parser(filename=document.original_filename, mime_type=document.file_type)
    except ValueError as exc:
        logger.error(
            "parse unsupported suffix document_id=%s original_filename=%s",
            document.id,
            document.original_filename,
        )
        raise DocumentParseError("Only .txt, .md, .docx, and .pdf documents are supported for parsing.") from exc

    try:
        parsed_document = parser.parse(
            source_path,
            filename=document.original_filename,
            mime_type=document.file_type,
        )
    except ValueError as exc:
        raise DocumentParseError(str(exc)) from exc
    extracted_text = blocks_to_text(parsed_document.blocks) if parsed_document.blocks else parsed_document.text
    parser_name = SUPPORTED_PARSE_SUFFIXES.get(
        suffix,
        str(parsed_document.metadata.get("parser") or parser.parser_name),
    )

    logger.info(
        "parse extracted text document_id=%s parser=%s extracted_char_count=%s",
        document.id,
        parser_name,
        len(extracted_text),
    )

    relative_path = build_parsed_relative_path(
        scope=scope,
        knowledge_base_id=document.knowledge_base_id,
        document_id=document.id,
        team_id=team_id,
    )
    destination = parsed_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "document_id": document.id,
        "knowledge_base_id": document.knowledge_base_id,
        "scope": scope.value,
        "team_id": team_id,
        "original_filename": document.original_filename,
        "source_storage_path": document.storage_path,
        "parser": parser_name,
        "extracted_char_count": len(extracted_text),
        "content": extracted_text,
        "blocks": [
            block.model_dump(mode="json")
            for block in parsed_document.blocks
        ],
    }
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        "parse completed document_id=%s destination=%s",
        document.id,
        destination,
    )
    return ParsedDocumentResult(
        parsed_path=relative_path.as_posix(),
        parser=parser_name,
        extracted_char_count=len(extracted_text),
    )


def build_parsed_relative_path(
    *,
    scope: KnowledgeBaseScope,
    knowledge_base_id: int,
    document_id: int,
    team_id: int | None = None,
) -> Path:
    filename = f"document_{document_id}.json"
    if scope == KnowledgeBaseScope.PERSONAL:
        return Path("personal") / f"knowledge_base_{knowledge_base_id}" / filename

    if team_id is None:
        raise ValueError("team_id is required for team document parsing.")

    return (
        Path("team")
        / f"team_{team_id}"
        / f"knowledge_base_{knowledge_base_id}"
        / filename
    )
