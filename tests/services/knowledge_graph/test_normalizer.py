from __future__ import annotations

from app.services.knowledge_graph.normalizer import normalize_entity_name


def test_normalize_entity_name_trims_and_lowercases_english() -> None:
    assert normalize_entity_name("  FastAPI   Service ") == "fastapi service"


def test_normalize_entity_name_preserves_chinese_text() -> None:
    assert normalize_entity_name(" 管理员 ") == "管理员"
