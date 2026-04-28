from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.provider_status import SystemProviderStatusRead
from app.services.provider_status import build_provider_status


router = APIRouter(tags=["system"])


@router.get("/")
async def read_root() -> dict[str, str]:
    settings = get_settings()
    return {
        "name": settings.app_name,
        "environment": settings.app_env,
        "stage": "phase-1-foundation",
        "message": "PureLink backend skeleton is running.",
    }


@router.get("/health")
async def health_check() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
    }


@router.get("/system/providers", response_model=SystemProviderStatusRead)
async def provider_status() -> SystemProviderStatusRead:
    return build_provider_status()
