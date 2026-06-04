"""Global FastAPI exception handlers for FNOL.

Mirrors the SDA handler shape; additionally classifies uncaught
`httpx.RequestError` (network/connection failures talking to SDA) as 502
"shared data api unreachable" so the dashboard sees a meaningful status
even if a route forgets to wrap its SDA call.

Routes that explicitly catch httpx errors retain their existing semantics —
this catch-all is defense-in-depth, not the primary path.
"""

import httpx
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging_setup import get_logger

log = get_logger("exception_handler")


def _request_context(request: Request, status_code: int) -> dict[str, object]:
    return {
        "user": getattr(request.state, "user_id", "-"),
        "method": request.method,
        "path": request.url.path,
        "status": status_code,
    }


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    log.info("http_exception", detail=exc.detail, **_request_context(request, exc.status_code))
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    log.warning(
        "request_validation_error",
        errors=exc.errors(),
        **_request_context(request, 422),
    )
    return JSONResponse({"detail": exc.errors()}, status_code=422)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, httpx.RequestError):
        log.warning(
            "shared_data_api_unreachable",
            error_class=exc.__class__.__name__,
            **_request_context(request, 502),
        )
        return JSONResponse({"detail": "shared data api unreachable"}, status_code=502)
    log.error(
        "unhandled_exception",
        error_class=exc.__class__.__name__,
        exc_info=exc,
        **_request_context(request, 500),
    )
    return JSONResponse({"detail": "internal server error"}, status_code=500)
