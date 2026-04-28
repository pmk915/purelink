from app.core.config import get_settings


def test_settings_accept_self_hosted_env_aliases(monkeypatch) -> None:
    monkeypatch.setenv("API_BASE_URL", "https://api.example.com/api/v1")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com,https://admin.example.com")
    monkeypatch.setenv("CHUNKS_DIR", "custom/chunks")
    monkeypatch.setenv("EMBEDDING_API_BASE_URL", "https://embedding.example.com/v1")
    monkeypatch.setenv("LLM_API_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("OCR_LANG", "chi_sim")
    monkeypatch.setenv("ASR_MODEL_PATH", "/models/vosk")

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.api_base_url == "https://api.example.com/api/v1"
    assert settings.frontend_base_url == "https://app.example.com"
    assert settings.cors_allow_origins == (
        "https://app.example.com",
        "https://admin.example.com",
    )
    assert settings.chunks_dir == "custom/chunks"
    assert settings.embedding_api_base == "https://embedding.example.com/v1"
    assert settings.llm_api_base == "https://llm.example.com/v1"
    assert settings.llm_timeout_seconds == 15.0
    assert settings.ocr_language == "chi_sim"
    assert settings.asr_vosk_model_path == "/models/vosk"

    get_settings.cache_clear()
