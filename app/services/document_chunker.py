from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

from app.models.document import Document
from app.models.enums import KnowledgeBaseScope
from app.services.document_parser import build_parsed_relative_path


DEFAULT_CHUNK_SIZE = 500


class DocumentChunkError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ChunkedDocumentResult:
    chunked_path: str
    source_parsed_path: str
    chunk_count: int
    chunk_size: int


def resolve_chunks_root(chunks_dir: str | Path, *, base_dir: Path) -> Path:
    chunks_root = Path(chunks_dir)
    if not chunks_root.is_absolute():
        chunks_root = base_dir / chunks_root
    return chunks_root


def chunk_document_from_parsed_result(
    *,
    document: Document,
    parsed_root: Path,
    chunks_root: Path,
    scope: KnowledgeBaseScope,
    team_id: int | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> ChunkedDocumentResult:
    parsed_relative_path = build_parsed_relative_path(
        scope=scope,
        knowledge_base_id=document.knowledge_base_id,
        document_id=document.id,
        team_id=team_id,
    )
    parsed_source = parsed_root / parsed_relative_path
    if not parsed_source.exists():
        raise DocumentChunkError("Parsed document result does not exist.")

    try:
        parsed_payload = json.loads(parsed_source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DocumentChunkError("Parsed document result is not valid JSON.") from exc

    content = parsed_payload.get("content")
    if not isinstance(content, str):
        raise DocumentChunkError("Parsed document result does not contain text content.")

    chunks = split_text_into_chunks(content, chunk_size=chunk_size)
    relative_path = build_chunk_relative_path(
        scope=scope,
        knowledge_base_id=document.knowledge_base_id,
        document_id=document.id,
        team_id=team_id,
    )
    destination = chunks_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "document_id": document.id,
        "knowledge_base_id": document.knowledge_base_id,
        "scope": scope.value,
        "team_id": team_id,
        "original_filename": parsed_payload.get(
            "original_filename",
            document.original_filename,
        ),
        "source_parsed_path": parsed_relative_path.as_posix(),
        "chunk_size": chunk_size,
        "chunk_count": len(chunks),
        "chunks": [
            {
                "index": index,
                "chunk_id": f"{document.id}:{index}",
                "char_count": len(text),
                "text": text,
            }
            for index, text in enumerate(chunks)
        ],
    }
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ChunkedDocumentResult(
        chunked_path=relative_path.as_posix(),
        source_parsed_path=parsed_relative_path.as_posix(),
        chunk_count=len(chunks),
        chunk_size=chunk_size,
    )


def split_text_into_chunks(text: str, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise DocumentChunkError("Parsed document contains no content to chunk.")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    blocks = [
        block.strip()
        for block in re.split(r"\n\s*\n", normalized)
        if block.strip()
    ]
    chunks: list[str] = []
    current_parts: list[str] = []
    current_length = 0

    for block in blocks:
        if len(block) > chunk_size:
            if current_parts:
                chunks.append("\n\n".join(current_parts))
                current_parts = []
                current_length = 0

            start = 0
            while start < len(block):
                piece = block[start:start + chunk_size].strip()
                if piece:
                    chunks.append(piece)
                start += chunk_size
            continue

        separator_length = 0 if not current_parts else 2
        tentative_length = current_length + separator_length + len(block)
        if tentative_length <= chunk_size:
            current_parts.append(block)
            current_length = tentative_length
        else:
            chunks.append("\n\n".join(current_parts))
            current_parts = [block]
            current_length = len(block)

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    if not chunks:
        raise DocumentChunkError("Parsed document contains no content to chunk.")
    return chunks


def build_chunk_relative_path(
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
        raise ValueError("team_id is required for team document chunking.")

    return (
        Path("team")
        / f"team_{team_id}"
        / f"knowledge_base_{knowledge_base_id}"
        / filename
    )
