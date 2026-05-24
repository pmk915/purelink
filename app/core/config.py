from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


def _load_env_file(env_file: Path = ENV_FILE) -> None:
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key:
            os.environ.setdefault(key, value)


def _get_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _get_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    values = tuple(
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    )
    return values or default


def _get_list_alias(
    names: tuple[str, ...],
    default: tuple[str, ...],
) -> tuple[str, ...]:
    for name in names:
        raw_value = os.getenv(name)
        if raw_value is None:
            continue

        values = tuple(
            item.strip()
            for item in raw_value.split(",")
            if item.strip()
        )
        if values:
            return values

    return default


def _get_str_alias(names: tuple[str, ...], default: str = "") -> str:
    values: list[str] = []
    for name in names:
        raw_value = os.getenv(name)
        if raw_value is None:
            continue
        value = raw_value.strip()
        if value:
            values.append(value)

    for value in values:
        if value != default:
            return value
    if values:
        return values[0]
    return default


def _get_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    return int(raw_value)


def _get_optional_int(name: str) -> int | None:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return None

    return int(raw_value)


def _get_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    return float(raw_value)


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_env: str
    app_debug: bool
    app_version: str
    log_level: str
    auth_secret_key: str
    auth_algorithm: str
    access_token_expire_minutes: int
    database_url: str
    redis_url: str
    api_base_url: str
    frontend_base_url: str
    db_echo: bool
    cors_allow_origins: tuple[str, ...]
    cors_allow_methods: tuple[str, ...]
    cors_allow_headers: tuple[str, ...]
    cors_allow_credentials: bool
    data_dir: str
    upload_dir: str
    parsed_dir: str
    chunks_dir: str
    vector_store_dir: str
    embedding_provider: str
    embedding_api_base: str
    embedding_api_key: str
    embedding_model: str
    embedding_device: str
    embedding_normalize: bool
    embedding_model_cache_dir: str
    embedding_timeout_seconds: float
    embedding_batch_size: int
    embedding_dimension: int | None
    enable_ocr: bool
    ocr_provider: str
    ocr_tesseract_command: str
    ocr_language: str
    ocr_tesseract_psm: int
    enable_media: bool
    asr_provider: str
    asr_ffmpeg_command: str
    asr_vosk_model_path: str
    multimodal_provider: str
    reranker_enabled: bool
    reranker_provider: str
    reranker_model: str
    reranker_top_n: int
    final_context_top_k: int
    retrieval_min_score: float
    overview_max_chunks: int
    overview_max_chunks_per_document: int
    conversation_recent_messages_limit: int
    conversation_context_max_chars: int
    conversation_message_max_chars: int
    citation_unit_min_chars: int
    citation_unit_target_chars: int
    citation_unit_max_chars: int
    citation_unit_max_sentences: int
    max_citations: int
    llm_provider: str
    llm_api_base: str
    llm_api_key: str
    llm_model: str
    llm_timeout_seconds: float
    llm_reasoning_effort: str
    llm_thinking_enabled: bool
    processing_queue_key: str
    processing_inflight_queue_key: str
    processing_queue_block_timeout_seconds: int
    processing_queue_recovery_interval_seconds: int
    processing_job_timeout_seconds: int
    max_upload_size_mb: int
    max_active_jobs_per_user: int
    max_active_jobs_per_kb: int


@lru_cache
def get_settings() -> Settings:
    _load_env_file()

    return Settings(
        app_name=os.getenv("APP_NAME", "PureLink"),
        app_env=os.getenv("APP_ENV", "development"),
        app_debug=_get_bool("APP_DEBUG", False),
        app_version=os.getenv("APP_VERSION", "0.1.0"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        auth_secret_key=os.getenv(
            "AUTH_SECRET_KEY",
            "purelink-dev-secret-key-change-me",
        ),
        auth_algorithm=os.getenv("AUTH_ALGORITHM", "HS256"),
        access_token_expire_minutes=_get_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://purelink:purelink@localhost:5432/purelink",
        ),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0").strip(),
        api_base_url=os.getenv(
            "API_BASE_URL",
            "http://localhost:8000/api/v1",
        ).strip(),
        frontend_base_url=os.getenv(
            "FRONTEND_BASE_URL",
            "http://localhost:3000",
        ).strip(),
        db_echo=_get_bool("DB_ECHO", False),
        cors_allow_origins=_get_list_alias(
            ("CORS_ORIGINS", "CORS_ALLOW_ORIGINS"),
            ("*",),
        ),
        cors_allow_methods=_get_list("CORS_ALLOW_METHODS", ("*",)),
        cors_allow_headers=_get_list("CORS_ALLOW_HEADERS", ("*",)),
        cors_allow_credentials=_get_bool("CORS_ALLOW_CREDENTIALS", False),
        data_dir=os.getenv("DATA_DIR", "data"),
        upload_dir=os.getenv("UPLOAD_DIR", "data/uploads"),
        parsed_dir=os.getenv("PARSED_DIR", "data/parsed"),
        chunks_dir=_get_str_alias(("CHUNKS_DIR", "CHUNK_DIR"), "data/chunks"),
        vector_store_dir=os.getenv("VECTOR_STORE_DIR", "data/vector_store"),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "fastembed").strip().lower(),
        embedding_api_base=_get_str_alias(
            ("EMBEDDING_API_BASE_URL", "EMBEDDING_API_BASE"),
        ),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY", "").strip(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5").strip(),
        embedding_device=os.getenv("EMBEDDING_DEVICE", "cpu").strip().lower(),
        embedding_normalize=_get_bool("EMBEDDING_NORMALIZE", True),
        embedding_model_cache_dir=os.getenv(
            "EMBEDDING_MODEL_CACHE_DIR",
            "/app/models/embedding",
        ).strip(),
        embedding_timeout_seconds=_get_float("EMBEDDING_TIMEOUT_SECONDS", 30.0),
        embedding_batch_size=_get_int("EMBEDDING_BATCH_SIZE", 32),
        embedding_dimension=_get_optional_int("EMBEDDING_DIMENSION"),
        enable_ocr=_get_bool("ENABLE_OCR", False),
        ocr_provider=os.getenv("OCR_PROVIDER", "disabled").strip().lower(),
        ocr_tesseract_command=os.getenv("OCR_TESSERACT_COMMAND", "tesseract").strip(),
        ocr_language=_get_str_alias(("OCR_LANG", "OCR_LANGUAGE"), "eng"),
        ocr_tesseract_psm=_get_int("OCR_TESSERACT_PSM", 6),
        enable_media=_get_bool("ENABLE_MEDIA", False),
        asr_provider=os.getenv("ASR_PROVIDER", "disabled").strip().lower(),
        asr_ffmpeg_command=os.getenv("ASR_FFMPEG_COMMAND", "ffmpeg").strip(),
        asr_vosk_model_path=_get_str_alias(
            ("ASR_MODEL_PATH", "ASR_VOSK_MODEL_PATH"),
            "/app/models/vosk",
        ).strip(),
        multimodal_provider=os.getenv("MULTIMODAL_PROVIDER", "disabled").strip().lower(),
        reranker_enabled=_get_bool("RERANKER_ENABLED", False),
        reranker_provider=os.getenv("RERANKER_PROVIDER", "noop").strip().lower(),
        reranker_model=os.getenv("RERANKER_MODEL", "").strip(),
        reranker_top_n=_get_int("RERANKER_TOP_N", 50),
        final_context_top_k=_get_int("FINAL_CONTEXT_TOP_K", 8),
        retrieval_min_score=_get_float("RETRIEVAL_MIN_SCORE", 0.15),
        overview_max_chunks=_get_int("OVERVIEW_MAX_CHUNKS", 10),
        overview_max_chunks_per_document=_get_int("OVERVIEW_MAX_CHUNKS_PER_DOCUMENT", 2),
        conversation_recent_messages_limit=_get_int(
            "CONVERSATION_RECENT_MESSAGES_LIMIT",
            8,
        ),
        conversation_context_max_chars=_get_int(
            "CONVERSATION_CONTEXT_MAX_CHARS",
            3000,
        ),
        conversation_message_max_chars=_get_int(
            "CONVERSATION_MESSAGE_MAX_CHARS",
            800,
        ),
        citation_unit_min_chars=_get_int("CITATION_UNIT_MIN_CHARS", 40),
        citation_unit_target_chars=_get_int("CITATION_UNIT_TARGET_CHARS", 120),
        citation_unit_max_chars=_get_int("CITATION_UNIT_MAX_CHARS", 300),
        citation_unit_max_sentences=_get_int("CITATION_UNIT_MAX_SENTENCES", 3),
        max_citations=_get_int("MAX_CITATIONS", 6),
        llm_provider=os.getenv("LLM_PROVIDER", "heuristic").strip().lower(),
        llm_api_base=_get_str_alias(("LLM_API_BASE_URL", "LLM_API_BASE")),
        llm_api_key=_get_str_alias(("LLM_API_KEY", "DEEPSEEK_API_KEY")),
        llm_model=os.getenv("LLM_MODEL", "").strip(),
        llm_timeout_seconds=_get_float("LLM_TIMEOUT_SECONDS", 30.0),
        llm_reasoning_effort=os.getenv("LLM_REASONING_EFFORT", "").strip().lower(),
        llm_thinking_enabled=_get_bool("LLM_THINKING_ENABLED", False),
        processing_queue_key=os.getenv(
            "PROCESSING_QUEUE_KEY",
            "purelink:processing-jobs:queued",
        ).strip(),
        processing_inflight_queue_key=os.getenv(
            "PROCESSING_INFLIGHT_QUEUE_KEY",
            "purelink:processing-jobs:inflight",
        ).strip(),
        processing_queue_block_timeout_seconds=_get_int(
            "PROCESSING_QUEUE_BLOCK_TIMEOUT_SECONDS",
            5,
        ),
        processing_queue_recovery_interval_seconds=_get_int(
            "PROCESSING_QUEUE_RECOVERY_INTERVAL_SECONDS",
            30,
        ),
        processing_job_timeout_seconds=_get_int(
            "PROCESSING_JOB_TIMEOUT_SECONDS",
            1800,
        ),
        max_upload_size_mb=_get_int("MAX_UPLOAD_SIZE_MB", 50),
        max_active_jobs_per_user=_get_int("MAX_ACTIVE_JOBS_PER_USER", 5),
        max_active_jobs_per_kb=_get_int("MAX_ACTIVE_JOBS_PER_KB", 10),
    )
