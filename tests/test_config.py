from app.core.config import get_settings


def test_settings_accept_self_hosted_env_aliases(monkeypatch) -> None:
    monkeypatch.setenv("API_BASE_URL", "https://api.example.com/api/v1")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com,https://admin.example.com")
    monkeypatch.setenv("CHUNKS_DIR", "custom/chunks")
    monkeypatch.setenv("EMBEDDING_API_BASE_URL", "https://embedding.example.com/v1")
    monkeypatch.setenv("EMBEDDING_DEVICE", "cuda")
    monkeypatch.setenv("EMBEDDING_NORMALIZE", "false")
    monkeypatch.setenv("EMBEDDING_MODEL_CACHE_DIR", "/models/embedding")
    monkeypatch.setenv("LLM_API_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "high")
    monkeypatch.setenv("LLM_THINKING_ENABLED", "true")
    monkeypatch.setenv("RETRIEVAL_MIN_SCORE", "0.22")
    monkeypatch.setenv("ENABLE_OCR", "true")
    monkeypatch.setenv("OCR_LANG", "chi_sim")
    monkeypatch.setenv("ENABLE_MEDIA", "true")
    monkeypatch.setenv("ASR_MODEL_PATH", "/models/vosk")
    monkeypatch.setenv("MULTIMODAL_PROVIDER", "disabled")
    monkeypatch.setenv("RERANKER_ENABLED", "false")
    monkeypatch.setenv("RERANKER_PROVIDER", "noop")
    monkeypatch.setenv("RERANKER_MODEL", "")
    monkeypatch.setenv("RERANKER_TOP_N", "40")
    monkeypatch.setenv("FINAL_CONTEXT_TOP_K", "7")

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
    assert settings.embedding_device == "cuda"
    assert settings.embedding_normalize is False
    assert settings.embedding_model_cache_dir == "/models/embedding"
    assert settings.llm_api_base == "https://llm.example.com/v1"
    assert settings.llm_timeout_seconds == 15.0
    assert settings.llm_reasoning_effort == "high"
    assert settings.llm_thinking_enabled is True
    assert settings.retrieval_min_score == 0.22
    assert settings.enable_ocr is True
    assert settings.ocr_language == "chi_sim"
    assert settings.enable_media is True
    assert settings.asr_vosk_model_path == "/models/vosk"
    assert settings.multimodal_provider == "disabled"
    assert settings.reranker_enabled is False
    assert settings.reranker_provider == "noop"
    assert settings.reranker_model == ""
    assert settings.reranker_top_n == 40
    assert settings.final_context_top_k == 7

    get_settings.cache_clear()
