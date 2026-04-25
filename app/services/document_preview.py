from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.document import (
    DocumentPreviewChunkRead,
    DocumentPreviewRead,
    DocumentRead,
)
from app.services.chunk_metadata import (
    build_chunk_snippet,
    infer_source_type_from_filename,
    parse_chunk_metadata,
)
from app.services.source_locator import (
    build_preview_target_for_chunk,
    build_source_locator_for_chunk,
)


def build_document_preview(
    db: Session,
    *,
    document: Document,
) -> DocumentPreviewRead:
    statement = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index.asc())
    )
    chunks = list(db.scalars(statement))
    fallback_source_type = infer_source_type_from_filename(document.original_filename)
    return DocumentPreviewRead(
        document=DocumentRead.model_validate(document),
        chunks=[
            _build_preview_chunk(
                chunk,
                document=document,
                fallback_source_type=fallback_source_type,
            )
            for chunk in chunks
        ],
    )


def resolve_document_file_path(
    *,
    upload_root: Path,
    document: Document,
) -> Path:
    return upload_root / document.storage_path


def _build_preview_chunk(
    chunk: DocumentChunk,
    *,
    document: Document,
    fallback_source_type: str,
) -> DocumentPreviewChunkRead:
    metadata = parse_chunk_metadata(
        chunk.metadata_json,
        fallback_source_type=fallback_source_type,
    )
    locator_source = SimpleNamespace(
        document_id=document.id,
        source_type=metadata.source_type,
        source_locator=metadata.source_locator,
        char_start=metadata.char_start,
        char_end=metadata.char_end,
        page_number=metadata.page_number,
        start_time=metadata.start_time,
        end_time=metadata.end_time,
        section_title=metadata.section_title,
        heading_path=metadata.heading_path,
        ocr_provider=metadata.ocr_provider,
    )
    return DocumentPreviewChunkRead(
        chunk_id=chunk.chunk_key,
        chunk_index=chunk.chunk_index,
        text=chunk.chunk_text,
        snippet=build_chunk_snippet(chunk.chunk_text),
        source_type=metadata.source_type,
        char_start=metadata.char_start,
        char_end=metadata.char_end,
        page_number=metadata.page_number,
        start_time=metadata.start_time,
        end_time=metadata.end_time,
        section_title=metadata.section_title,
        source_locator=build_source_locator_for_chunk(locator_source),
        preview_target=build_preview_target_for_chunk(locator_source),
        heading_path=list(metadata.heading_path) if metadata.heading_path else None,
    )
