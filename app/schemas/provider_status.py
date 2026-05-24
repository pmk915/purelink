from __future__ import annotations

from pydantic import BaseModel


class ProviderStatusRead(BaseModel):
    provider: str
    configured: bool
    requires_api_key: bool
    mode: str
    message: str
    model: str | None = None
    model_name: str | None = None
    base_url_configured: bool | None = None
    api_key_configured: bool | None = None
    model_path_exists: bool | None = None
    binary_available: bool | None = None
    enabled: bool | None = None
    available: bool | None = None
    error: str | None = None


class SystemProviderStatusRead(BaseModel):
    llm: ProviderStatusRead
    embedding: ProviderStatusRead
    ocr: ProviderStatusRead
    asr: ProviderStatusRead
    reranker: ProviderStatusRead
