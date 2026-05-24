from __future__ import annotations

import json
import subprocess

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app


@pytest.mark.anyio
async def test_provider_status_local_fallback_is_configured(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "heuristic")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local_hashed_bow")
    monkeypatch.setenv("ENABLE_OCR", "false")
    monkeypatch.setenv("OCR_PROVIDER", "disabled")
    monkeypatch.setenv("ENABLE_MEDIA", "false")
    monkeypatch.setenv("ASR_PROVIDER", "disabled")
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    monkeypatch.setenv("RERANKER_PROVIDER", "noop")
    get_settings.cache_clear()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/system/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["configured"] is True
    assert payload["llm"]["requires_api_key"] is False
    assert payload["llm"]["mode"] == "local_demo"
    assert payload["embedding"]["configured"] is True
    assert payload["embedding"]["requires_api_key"] is False
    assert payload["embedding"]["mode"] == "local_demo"
    assert payload["ocr"]["mode"] == "disabled"
    assert payload["asr"]["mode"] == "disabled"
    assert payload["reranker"]["mode"] == "disabled"
    assert payload["reranker"]["enabled"] is False
    assert payload["reranker"]["provider"] == "noop"

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_provider_status_reranker_local_rule_can_be_enabled(monkeypatch) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "true")
    monkeypatch.setenv("RERANKER_PROVIDER", "local_rule_reranker")
    get_settings.cache_clear()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/system/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["reranker"]["configured"] is True
    assert payload["reranker"]["mode"] == "local_demo"
    assert payload["reranker"]["enabled"] is True
    assert payload["reranker"]["model_name"] == "local_rule_reranker"

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_provider_status_flagembedding_missing_dependency_is_not_500(
    monkeypatch,
) -> None:
    monkeypatch.setenv("RERANKER_ENABLED", "true")
    monkeypatch.setenv("RERANKER_PROVIDER", "flagembedding")
    monkeypatch.setenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
    get_settings.cache_clear()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/system/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["reranker"]["provider"] == "flagembedding"
    assert payload["reranker"]["enabled"] is True
    assert payload["reranker"]["model_name"] == "BAAI/bge-reranker-v2-m3"
    if payload["reranker"]["available"] is False:
        assert "FlagEmbedding is required" in payload["reranker"]["error"]

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_provider_status_external_missing_key_is_clear(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "chat-model")
    get_settings.cache_clear()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/system/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["configured"] is False
    assert payload["llm"]["requires_api_key"] is True
    assert payload["llm"]["api_key_configured"] is False
    assert "LLM_API_KEY" in payload["llm"]["message"]

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_provider_status_deepseek_is_clear(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("LLM_API_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_API_KEY", "deepseek-secret")
    monkeypatch.setenv("LLM_MODEL", "deepseek-v4-pro")
    get_settings.cache_clear()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/system/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["configured"] is True
    assert payload["llm"]["requires_api_key"] is True
    assert payload["llm"]["mode"] == "external_api"
    assert payload["llm"]["provider"] == "deepseek"
    assert payload["llm"]["model"] == "deepseek-v4-pro"

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_provider_status_fastembed_is_local_model(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fastembed")
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    get_settings.cache_clear()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/system/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embedding"]["configured"] is True
    assert payload["embedding"]["requires_api_key"] is False
    assert payload["embedding"]["mode"] == "local_model"
    assert payload["embedding"]["model"] == "BAAI/bge-small-zh-v1.5"

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_provider_status_does_not_expose_api_keys(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "llm-secret-value")
    monkeypatch.setenv("LLM_MODEL", "chat-model")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EMBEDDING_API_BASE_URL", "https://embedding.example.com/v1")
    monkeypatch.setenv("EMBEDDING_API_KEY", "embedding-secret-value")
    monkeypatch.setenv("EMBEDDING_MODEL", "embedding-model")
    get_settings.cache_clear()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/system/providers")

    assert response.status_code == 200
    encoded = json.dumps(response.json(), ensure_ascii=False)
    assert "llm-secret-value" not in encoded
    assert "embedding-secret-value" not in encoded
    assert response.json()["llm"]["api_key_configured"] is True
    assert response.json()["embedding"]["api_key_configured"] is True

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_provider_status_unsupported_provider_is_not_500(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "unknown_llm")
    get_settings.cache_clear()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/system/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["llm"]["configured"] is False
    assert payload["llm"]["mode"] == "unsupported"
    assert "不支持" in payload["llm"]["message"]

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_provider_status_sentence_transformers_optional_mode_is_clear(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    get_settings.cache_clear()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/system/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embedding"]["configured"] is True
    assert payload["embedding"]["mode"] == "local_model"
    assert payload["embedding"]["model"] == "BAAI/bge-small-zh-v1.5"

    get_settings.cache_clear()


def test_check_stack_script_syntax() -> None:
    completed = subprocess.run(
        ["bash", "-n", "scripts/check_stack.sh"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
