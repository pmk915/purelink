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
    db_echo: bool
    cors_allow_origins: tuple[str, ...]
    cors_allow_methods: tuple[str, ...]
    cors_allow_headers: tuple[str, ...]
    cors_allow_credentials: bool
    upload_dir: str
    parsed_dir: str
    chunks_dir: str
    vector_store_dir: str
    llm_provider: str
    llm_api_base: str
    llm_api_key: str
    llm_model: str


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
        db_echo=_get_bool("DB_ECHO", False),
        cors_allow_origins=_get_list("CORS_ALLOW_ORIGINS", ("*",)),
        cors_allow_methods=_get_list("CORS_ALLOW_METHODS", ("*",)),
        cors_allow_headers=_get_list("CORS_ALLOW_HEADERS", ("*",)),
        cors_allow_credentials=_get_bool("CORS_ALLOW_CREDENTIALS", False),
        upload_dir=os.getenv("UPLOAD_DIR", "data/uploads"),
        parsed_dir=os.getenv("PARSED_DIR", "data/parsed"),
        chunks_dir=os.getenv("CHUNK_DIR", "data/chunks"),
        vector_store_dir=os.getenv("VECTOR_STORE_DIR", "data/vector_store"),
        llm_provider=os.getenv("LLM_PROVIDER", "heuristic").strip().lower(),
        llm_api_base=os.getenv("LLM_API_BASE", "").strip(),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "").strip(),
    )
