from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.document import Document
from app.models.enums import (
    DocumentProcessingStatus,
    DocumentReviewStatus,
    KnowledgeBaseScope,
)
from app.services.document_chunker import build_chunk_relative_path
from app.services.document_embedding import (
    DocumentEmbeddingError,
    build_index_relative_path,
    describe_index_metadata_mismatch,
    embed_document_chunks,
    read_knowledge_base_index_metadata,
)
from app.services.embedding_provider import resolve_embedding_provider


def _build_document(*, document_id: int, knowledge_base_id: int, original_filename: str) -> Document:
    return Document(
        id=document_id,
        knowledge_base_id=knowledge_base_id,
        owner_id=1,
        submitted_by=1,
        filename=original_filename,
        original_filename=original_filename,
        file_type="text/plain",
        file_size=64,
        storage_path=f"personal/knowledge_base_{knowledge_base_id}/{original_filename}",
        review_status=DocumentReviewStatus.NOT_REQUIRED,
        processing_status=DocumentProcessingStatus.READY,
    )


def _write_chunk_payload(
    *,
    chunks_root: Path,
    knowledge_base_id: int,
    document_id: int,
    text: str,
) -> None:
    relative_path = build_chunk_relative_path(
        scope=KnowledgeBaseScope.PERSONAL,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
    )
    destination = chunks_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "chunks": [
                    {
                        "chunk_id": f"document-{document_id}-chunk-0",
                        "text": text,
                        "metadata": {"source_type": "text"},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_embed_document_chunks_writes_index_metadata(tmp_path: Path) -> None:
    chunks_root = tmp_path / "chunks"
    vector_root = tmp_path / "vector_store"
    document = _build_document(
        document_id=11,
        knowledge_base_id=7,
        original_filename="semantic-demo.txt",
    )
    _write_chunk_payload(
        chunks_root=chunks_root,
        knowledge_base_id=document.knowledge_base_id,
        document_id=document.id,
        text="PureLink writes index metadata for local hashed bow.",
    )

    result = embed_document_chunks(
        document=document,
        chunks_root=chunks_root,
        vector_root=vector_root,
        scope=KnowledgeBaseScope.PERSONAL,
        provider=resolve_embedding_provider("local_hashed_bow"),
    )

    metadata = read_knowledge_base_index_metadata(
        vector_root=vector_root,
        scope=KnowledgeBaseScope.PERSONAL,
        knowledge_base_id=document.knowledge_base_id,
    )
    assert metadata is not None
    assert result.embedding_provider == "local_hashed_bow"
    assert metadata["embedding_provider"] == "local_hashed_bow"
    assert metadata["embedding_model"] == "hashed_bow_v1"
    assert metadata["embedding_dimension"] == 128
    assert metadata["embedding_normalize"] is True
    assert isinstance(metadata["created_at"], str)


def test_embed_document_chunks_writes_fastembed_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks_root = tmp_path / "chunks"
    vector_root = tmp_path / "vector_store"
    document = _build_document(
        document_id=12,
        knowledge_base_id=8,
        original_filename="semantic-fastembed.txt",
    )
    _write_chunk_payload(
        chunks_root=chunks_root,
        knowledge_base_id=document.knowledge_base_id,
        document_id=document.id,
        text="PureLink writes index metadata for fastembed.",
    )

    class FakeFastEmbedModel:
        def embed(self, texts, *, batch_size):
            assert batch_size == 32
            return [[1.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(
        "app.services.embedding_provider._load_fastembed_model",
        lambda **kwargs: FakeFastEmbedModel(),
    )

    result = embed_document_chunks(
        document=document,
        chunks_root=chunks_root,
        vector_root=vector_root,
        scope=KnowledgeBaseScope.PERSONAL,
        provider=resolve_embedding_provider("fastembed", model="BAAI/bge-small-zh-v1.5"),
    )

    metadata = read_knowledge_base_index_metadata(
        vector_root=vector_root,
        scope=KnowledgeBaseScope.PERSONAL,
        knowledge_base_id=document.knowledge_base_id,
    )
    assert metadata is not None
    assert result.embedding_provider == "fastembed"
    assert metadata["embedding_provider"] == "fastembed"
    assert metadata["embedding_model"] == "BAAI/bge-small-zh-v1.5"
    assert metadata["embedding_dimension"] == 3
    assert metadata["embedding_normalize"] is True


def test_describe_index_metadata_mismatch_reports_reindex_requirement() -> None:
    provider = resolve_embedding_provider(
        "sentence_transformers",
        model="BAAI/bge-m3",
        device="cpu",
        normalize=True,
        cache_dir="/tmp/embedding-cache",
    )

    mismatch = describe_index_metadata_mismatch(
        {
            "embedding_provider": "sentence_transformers",
            "embedding_model": "BAAI/bge-small-zh-v1.5",
            "embedding_dimension": 512,
            "embedding_normalize": True,
            "documents": [],
        },
        provider=provider,
        query_dimension=1024,
    )

    assert mismatch is not None
    assert "Reindex is required" in mismatch
    assert "embedding_model" in mismatch
    assert "embedding_dimension" in mismatch


def test_embed_document_chunks_rejects_mixed_knowledge_base_reindex(tmp_path: Path) -> None:
    chunks_root = tmp_path / "chunks"
    vector_root = tmp_path / "vector_store"
    knowledge_base_id = 9
    document = _build_document(
        document_id=21,
        knowledge_base_id=knowledge_base_id,
        original_filename="reindex-me.txt",
    )
    _write_chunk_payload(
        chunks_root=chunks_root,
        knowledge_base_id=knowledge_base_id,
        document_id=document.id,
        text="PureLink should reject mixed embedding metadata in one knowledge base.",
    )

    index_path = vector_root / build_index_relative_path(
        scope=KnowledgeBaseScope.PERSONAL,
        knowledge_base_id=knowledge_base_id,
    )
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(
            {
                "embedding_provider": "local_hashed_bow",
                "embedding_model": "hashed_bow_v1",
                "embedding_version": "hashed_bow_v1",
                "embedding_dimension": 128,
                "embedding_normalize": True,
                "documents": [
                    {
                        "document_id": 21,
                        "embedding_provider": "local_hashed_bow",
                        "embedding_model": "hashed_bow_v1",
                        "embedding_dimension": 128,
                        "embedding_normalize": True,
                        "chunks": [],
                    },
                    {
                        "document_id": 22,
                        "embedding_provider": "local_hashed_bow",
                        "embedding_model": "hashed_bow_v1",
                        "embedding_dimension": 128,
                        "embedding_normalize": True,
                        "chunks": [],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        DocumentEmbeddingError,
        match="Reindex the knowledge base instead of a single document",
    ):
        embed_document_chunks(
            document=document,
            chunks_root=chunks_root,
            vector_root=vector_root,
            scope=KnowledgeBaseScope.PERSONAL,
            dimension=64,
            provider=resolve_embedding_provider("local_hashed_bow"),
        )
