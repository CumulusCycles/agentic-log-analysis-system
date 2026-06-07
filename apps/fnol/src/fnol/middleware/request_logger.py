import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from ..logging_setup import get_logger

log = get_logger("request")


def _normalize_source(raw: str | None) -> str:
    """Coerce the inbound `X-Source` header to the canonical lowercase value.
    Missing / blank → `unknown`. Real UX traffic must tag `prod` explicitly
    from the React SPA (ADR-011 2026-06-07 amendment)."""
    if raw is None:
        return "unknown"
    stripped = raw.strip().lower()
    return stripped or "unknown"


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """Reads `X-Source` and binds it onto `structlog.contextvars` so EVERY
    structlog event emitted during the request lifetime (including domain
    events like `sda_upstream_rejected`) picks up `source` via
    `merge_contextvars`. The outbound `SharedDataAPIClient` reads the same
    contextvar to forward `X-Source` on its call to SDA — keeping the source
    chain unbroken across the FNOL → SDA hop. See ADR-011."""

    async def dispatch(self, request: Request, call_next):
        structlog.contextvars.clear_contextvars()
        source = _normalize_source(request.headers.get("X-Source"))
        structlog.contextvars.bind_contextvars(source=source)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            # `source` is also passed explicitly so `structlog.testing.capture_logs`
            # in tests sees it without depending on `merge_contextvars`.
            log.info(
                "request",
                # FNOL is the edge — no upstream caller. user_id is set by the
                # JWT dependency when one is required.
                caller="-",
                source=source,
                user=getattr(request.state, "user_id", "-"),
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            )
            return response
        finally:
            structlog.contextvars.clear_contextvars()
