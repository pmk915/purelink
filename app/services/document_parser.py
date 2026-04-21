from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path

from app.models.document import Document
from app.models.enums import KnowledgeBaseScope


SUPPORTED_PARSE_SUFFIXES = {
    ".txt": "plain_text",
    ".md": "markdown",
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
    parser = SUPPORTED_PARSE_SUFFIXES.get(suffix)
    if parser is None:
        logger.error(
            "parse unsupported suffix document_id=%s original_filename=%s",
            document.id,
            document.original_filename,
        )
        raise DocumentParseError("Only .txt and .md documents are supported for parsing.")

    try:
        extracted_text = source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        logger.exception(
            "parse decode failed document_id=%s source_path=%s",
            document.id,
            source_path,
        )
        raise DocumentParseError("Document could not be decoded as UTF-8 text.") from exc

    logger.info(
        "parse extracted text document_id=%s parser=%s extracted_char_count=%s",
        document.id,
        parser,
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
        "parser": parser,
        "extracted_char_count": len(extracted_text),
        "content": extracted_text,
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
        parser=parser,
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
