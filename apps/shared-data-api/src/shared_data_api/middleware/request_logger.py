import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from ..logging_setup import get_logger

log = get_logger("request")


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        log.info(
            "request",
            caller=getattr(request.state, "caller", "-"),
            user=getattr(request.state, "user_id", "-"),
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response
