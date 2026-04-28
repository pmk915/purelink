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
    tmp_path,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "heuristic")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local_hashed_bow")
    monkeypatch.setenv("OCR_PROVIDER", "tesseract")
    monkeypatch.setenv("OCR_TESSERACT_COMMAND", "python3")
    monkeypatch.setenv("ASR_PROVIDER", "vosk")
    monkeypatch.setenv("ASR_MODEL_PATH", str(tmp_path))
    monkeypatch.setenv("ASR_FFMPEG_COMMAND", "python3")
    monkeypatch.setenv("RERANKER_PROVIDER", "local_rule_reranker")
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
    assert payload["asr"]["configured"] is True

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
async def test_provider_status_reports_missing_asr_model(monkeypatch, tmp_path) -> None:
    missing_path = tmp_path / "missing-vosk-model"
    monkeypatch.setenv("ASR_PROVIDER", "vosk")
    monkeypatch.setenv("ASR_MODEL_PATH", str(missing_path))
    monkeypatch.setenv("ASR_FFMPEG_COMMAND", "python3")
    get_settings.cache_clear()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/system/providers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["asr"]["configured"] is False
    assert payload["asr"]["model_path_exists"] is False
    assert "模型路径不存在" in payload["asr"]["message"]

    get_settings.cache_clear()


def test_check_stack_script_syntax() -> None:
    completed = subprocess.run(
        ["bash", "-n", "scripts/check_stack.sh"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
