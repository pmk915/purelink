from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document_block import DocumentBlock as DocumentBlockModel
from app.services.document_parsing.types import DocumentBlock


def replace_document_blocks(
    db: Session,
    *,
    document_id: int,
    blocks: list[DocumentBlock],
) -> list[DocumentBlockModel]:
    db.execute(delete(DocumentBlockModel).where(DocumentBlockModel.document_id == document_id))
    saved_blocks: list[DocumentBlockModel] = []
    for block in sorted(blocks, key=lambda item: item.order_index):
        saved = DocumentBlockModel(
            document_id=document_id,
            block_type=block.block_type,
            text=block.text,
            source_locator=block.source_locator,
            order_index=block.order_index,
            heading_level=block.heading_level,
            metadata_json=(
                json.dumps(block.metadata, ensure_ascii=False, sort_keys=True)
                if block.metadata
                else None
            ),
        )
        db.add(saved)
        saved_blocks.append(saved)
    db.flush()
    return saved_blocks


def list_document_blocks(
    db: Session,
    *,
    document_id: int,
) -> list[DocumentBlockModel]:
    return list(
        db.scalars(
            select(DocumentBlockModel)
            .where(DocumentBlockModel.document_id == document_id)
            .order_by(DocumentBlockModel.order_index.asc())
        )
    )
