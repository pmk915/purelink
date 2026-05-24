from __future__ import annotations

from app.services.knowledge_graph.graph_extractor import extract_graph_from_sources
from app.services.knowledge_graph.types import GraphSourceText


def test_local_rule_graph_extractor_extracts_entities_and_grounded_relations() -> None:
    result = extract_graph_from_sources(
        [
            GraphSourceText(
                document_id=1,
                chunk_id=10,
                citation_unit_id=20,
                text="管理员可以删除团队文档，普通成员可以上传文档。FastAPI 使用 PostgreSQL。",
                source_locator="heading:权限",
            )
        ]
    )

    entity_names = {item.name for item in result.entities}
    relation_types = {item.relation_type for item in result.relations}

    assert "管理员" in entity_names
    assert "文档" in entity_names
    assert "FastAPI" in entity_names
    assert "can_delete" in relation_types
    assert "can_upload" in relation_types
    assert result.mentions
    assert all(item.source_document_id == 1 for item in result.relations)
    assert all(item.source_chunk_id == 10 for item in result.relations)
