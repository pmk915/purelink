from __future__ import annotations

from http import HTTPStatus
import logging
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response


logger = logging.getLogger("purelink.exceptions")

REQUEST_ID_HEADER = "X-Request-ID"

STATUS_CODE_TO_ERROR_CODE = {
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "RESOURCE_NOT_FOUND",
    409: "CONFLICT",
    413: "UPLOAD_TOO_LARGE",
    415: "UNSUPPORTED_FILE_TYPE",
    422: "VALIDATION_ERROR",
}


def register_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or f"req_{uuid4().hex}"
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id

    request_id = request.headers.get(REQUEST_ID_HEADER) or f"req_{uuid4().hex}"
    request.state.request_id = request_id
    return request_id


def _default_error_code(status_code: int) -> str:
    if status_code in STATUS_CODE_TO_ERROR_CODE:
        return STATUS_CODE_TO_ERROR_CODE[status_code]
    if 400 <= status_code < 500:
        return "BAD_REQUEST"
    return "INTERNAL_ERROR"


def _default_message(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Request failed"


def _normalize_http_detail(
    status_code: int,
    detail: Any,
) -> tuple[str, str, dict[str, Any] | None]:
    error_code = _default_error_code(status_code)
    message = _default_message(status_code)
    details: dict[str, Any] | None = None

    if isinstance(detail, str):
        message = detail or message
    elif isinstance(detail, dict):
        raw_code = detail.get("code") or detail.get("error_code")
        raw_message = detail.get("message") or detail.get("detail")
        if isinstance(raw_code, str) and raw_code:
            error_code = raw_code
        if isinstance(raw_message, str) and raw_message:
            message = raw_message

        extra = {
            key: value
            for key, value in detail.items()
            if key not in {"code", "error_code", "message", "detail"}
        }
        details = extra or None
    elif detail is not None:
        message = str(detail)

    return error_code, message, details


def _validation_details(exc: RequestValidationError) -> dict[str, Any]:
    return {
        "errors": [
            {
                "loc": list(error.get("loc", [])),
                "msg": error.get("msg", "Invalid input"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
    }


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    response_headers = dict(headers or {})
    response_headers[REQUEST_ID_HEADER] = request_id
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
        }
    }
    return JSONResponse(
        status_code=status_code,
        content=body,
        headers=response_headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        code, message, details = _normalize_http_detail(exc.status_code, exc.detail)
        return _error_response(
            request,
            status_code=exc.status_code,
            code=code,
            message=message,
            details=details,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            request,
            status_code=422,
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            details=_validation_details(exc),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        request_id = _request_id(request)
        logger.exception(
            "Unhandled exception request_id=%s path=%s",
            request_id,
            request.url.path,
        )
        return _error_response(
            request,
            status_code=500,
            code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
        )
