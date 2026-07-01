from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import pytest
from fastapi import Body, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.main import app


class ValidationPayload(BaseModel):
    name: str


@asynccontextmanager
async def temporary_route(
    path: str,
    endpoint: Callable[..., object],
    *,
    methods: list[str] | None = None,
) -> AsyncIterator[None]:
    original_routes = list(app.router.routes)
    app.add_api_route(path, endpoint, methods=methods or ["GET"])
    try:
        yield
    finally:
        app.router.routes[:] = original_routes


async def get_test_client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        yield client


@pytest.mark.anyio
async def test_404_http_exception_returns_error_envelope() -> None:
    async def endpoint() -> None:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")

    async with temporary_route("/__test/error-404", endpoint):
        async for client in get_test_client():
            response = await client.get("/__test/error-404")

    assert response.status_code == 404
    assert response.headers["X-Request-ID"].startswith("req_")
    payload = response.json()
    assert payload["error"]["code"] == "RESOURCE_NOT_FOUND"
    assert payload["error"]["message"] == "Knowledge base not found."
    assert payload["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.anyio
async def test_403_maps_to_forbidden() -> None:
    async def endpoint() -> None:
        raise HTTPException(status_code=403, detail="Permission denied.")

    async with temporary_route("/__test/error-403", endpoint):
        async for client in get_test_client():
            response = await client.get("/__test/error-403")

    assert response.status_code == 403
    payload = response.json()
    assert payload["error"]["code"] == "FORBIDDEN"
    assert payload["error"]["message"] == "Permission denied."


@pytest.mark.anyio
async def test_validation_error_returns_validation_error_envelope() -> None:
    async def endpoint(payload: ValidationPayload = Body(...)) -> dict[str, str]:
        return {"name": payload.name}

    async with temporary_route("/__test/validation", endpoint, methods=["POST"]):
        async for client in get_test_client():
            response = await client.post("/__test/validation", json={})

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["message"] == "Request validation failed."
    assert payload["error"]["details"]["errors"][0]["loc"] == ["body", "name"]


@pytest.mark.anyio
async def test_unhandled_exception_returns_internal_error_without_traceback() -> None:
    async def endpoint() -> None:
        raise RuntimeError("database password leaked in stack")

    async with temporary_route("/__test/unhandled", endpoint):
        async for client in get_test_client():
            response = await client.get("/__test/unhandled")

    assert response.status_code == 500
    payload = response.json()
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert payload["error"]["message"] == "An unexpected error occurred."
    response_text = response.text.lower()
    assert "traceback" not in response_text
    assert "database password" not in response_text


@pytest.mark.anyio
async def test_request_id_header_is_propagated_to_response_and_body() -> None:
    async def endpoint() -> None:
        raise HTTPException(status_code=404, detail="Missing.")

    async with temporary_route("/__test/request-id", endpoint):
        async for client in get_test_client():
            response = await client.get(
                "/__test/request-id",
                headers={"X-Request-ID": "req_test_123"},
            )

    assert response.headers["X-Request-ID"] == "req_test_123"
    assert response.json()["error"]["request_id"] == "req_test_123"


@pytest.mark.anyio
async def test_detail_dict_preserves_business_code_and_message() -> None:
    async def endpoint() -> None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DOCUMENT_NOT_READY",
                "message": "Document is not ready for retrieval.",
                "document_id": 42,
            },
        )

    async with temporary_route("/__test/business-code", endpoint):
        async for client in get_test_client():
            response = await client.get("/__test/business-code")

    assert response.status_code == 409
    payload = response.json()
    assert payload["error"]["code"] == "DOCUMENT_NOT_READY"
    assert payload["error"]["message"] == "Document is not ready for retrieval."
    assert payload["error"]["details"] == {"document_id": 42}
