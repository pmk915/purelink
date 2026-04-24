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
    db_echo: bool
    cors_allow_origins: tuple[str, ...]
    cors_allow_methods: tuple[str, ...]
    cors_allow_headers: tuple[str, ...]
    cors_allow_credentials: bool
    upload_dir: str
    parsed_dir: str
    chunks_dir: str
    vector_store_dir: str
    embedding_provider: str
    embedding_api_base: str
    embedding_api_key: str
    embedding_model: str
    embedding_timeout_seconds: float
    embedding_batch_size: int
    embedding_dimension: int | None
    ocr_provider: str
    ocr_tesseract_command: str
    ocr_language: str
    ocr_tesseract_psm: int
    asr_provider: str
    asr_ffmpeg_command: str
    asr_vosk_model_path: str
    reranker_enabled: bool
    reranker_provider: str
    llm_provider: str
    llm_api_base: str
    llm_api_key: str
    llm_model: str
    processing_queue_key: str
    processing_inflight_queue_key: str
    processing_queue_block_timeout_seconds: int


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
        db_echo=_get_bool("DB_ECHO", False),
        cors_allow_origins=_get_list("CORS_ALLOW_ORIGINS", ("*",)),
        cors_allow_methods=_get_list("CORS_ALLOW_METHODS", ("*",)),
        cors_allow_headers=_get_list("CORS_ALLOW_HEADERS", ("*",)),
        cors_allow_credentials=_get_bool("CORS_ALLOW_CREDENTIALS", False),
        upload_dir=os.getenv("UPLOAD_DIR", "data/uploads"),
        parsed_dir=os.getenv("PARSED_DIR", "data/parsed"),
        chunks_dir=os.getenv("CHUNK_DIR", "data/chunks"),
        vector_store_dir=os.getenv("VECTOR_STORE_DIR", "data/vector_store"),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "local_hashed_bow").strip().lower(),
        embedding_api_base=os.getenv("EMBEDDING_API_BASE", "").strip(),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY", "").strip(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "").strip(),
        embedding_timeout_seconds=_get_float("EMBEDDING_TIMEOUT_SECONDS", 30.0),
        embedding_batch_size=_get_int("EMBEDDING_BATCH_SIZE", 32),
        embedding_dimension=_get_optional_int("EMBEDDING_DIMENSION"),
        ocr_provider=os.getenv("OCR_PROVIDER", "tesseract").strip().lower(),
        ocr_tesseract_command=os.getenv("OCR_TESSERACT_COMMAND", "tesseract").strip(),
        ocr_language=os.getenv("OCR_LANGUAGE", "eng").strip(),
        ocr_tesseract_psm=_get_int("OCR_TESSERACT_PSM", 6),
        asr_provider=os.getenv("ASR_PROVIDER", "vosk").strip().lower(),
        asr_ffmpeg_command=os.getenv("ASR_FFMPEG_COMMAND", "ffmpeg").strip(),
        asr_vosk_model_path=os.getenv(
            "ASR_VOSK_MODEL_PATH",
            "/opt/vosk/vosk-model-small-en-us-0.15",
        ).strip(),
        reranker_enabled=_get_bool("RERANKER_ENABLED", True),
        reranker_provider=os.getenv("RERANKER_PROVIDER", "local_rule_reranker").strip().lower(),
        llm_provider=os.getenv("LLM_PROVIDER", "heuristic").strip().lower(),
        llm_api_base=os.getenv("LLM_API_BASE", "").strip(),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "").strip(),
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
    )
