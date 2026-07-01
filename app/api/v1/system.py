from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.document import UploadConstraintsRead
from app.schemas.provider_status import SystemProviderStatusRead
from app.services.provider_status import build_provider_status
from app.services.upload_guard import build_upload_constraints


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


@router.get("/upload/constraints", response_model=UploadConstraintsRead)
async def upload_constraints() -> UploadConstraintsRead:
    settings = get_settings()
    constraints = build_upload_constraints(
        max_upload_size_mb=settings.max_upload_size_mb,
        allowed_extensions=settings.allowed_upload_extensions,
        allowed_mime_types=settings.allowed_upload_mime_types,
    )
    return UploadConstraintsRead(
        max_upload_size_mb=constraints.max_upload_size_mb,
        max_upload_size_bytes=constraints.max_upload_size_bytes,
        allowed_extensions=list(constraints.allowed_extensions),
        allowed_mime_types=list(constraints.allowed_mime_types),
    )
