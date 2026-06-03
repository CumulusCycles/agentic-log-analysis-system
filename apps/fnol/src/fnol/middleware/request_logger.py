import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..logging_setup import get_logger

log = get_logger("request")


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        log.info(
            "request",
            # FNOL is the edge — no upstream caller. user_id is set by the
            # JWT dependency when one is required.
            caller="-",
            user=getattr(request.state, "user_id", "-"),
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response
