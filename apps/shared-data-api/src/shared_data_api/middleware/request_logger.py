import time

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from ..logging_setup import get_logger

log = get_logger("request")


def _normalize_source(raw: str | None) -> str:
    """Coerce an incoming `X-Source` header into the lowercase string the
    dashboard's ingest gate expects (`prod` / `synthetic` / `test` / `health`).
    Missing or whitespace-only header → `prod` (default for real-user traffic).
    """
    if raw is None:
        return "prod"
    stripped = raw.strip().lower()
    return stripped or "prod"


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """Per-request middleware that:

    1. Reads `X-Source` from the inbound request headers (default `prod`).
    2. Binds it onto `structlog.contextvars` so EVERY structlog event emitted
       during the request lifetime — domain events like `login_failed`,
       `claim_created`, anything raised through `log.warning(...)` — picks up
       `source` automatically via `merge_contextvars` in the processor chain.
       Without this, only the synthesised `event=request` line at the end
       carried the tag; domain WARN/ERROR events defaulted to `prod` in the
       dashboard parser regardless of the real traffic origin.
    3. Emits the `event=request` summary at the tail. `source` is already in
       the contextvars dict, so `merge_contextvars` adds it — no explicit
       kwarg needed.
    4. Clears the contextvars at the START of every dispatch so a misbehaving
       prior task (or a starlette quirk) can't leak source across requests.
    """

    async def dispatch(self, request: Request, call_next):
        structlog.contextvars.clear_contextvars()
        source = _normalize_source(request.headers.get("X-Source"))
        structlog.contextvars.bind_contextvars(source=source)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            # `source` is also passed explicitly so `structlog.testing.capture_logs`
            # in tests sees it without depending on `merge_contextvars` running
            # (capture intercepts before processors). Domain events emitted
            # from inside `call_next` get `source` via the contextvar binding.
            log.info(
                "request",
                caller=getattr(request.state, "caller", "-"),
                source=source,
                user=getattr(request.state, "user_id", "-"),
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            )
            return response
        finally:
            # Always clear, even if `call_next` raised — prevents leakage
            # into the next request handled by this worker.
            structlog.contextvars.clear_contextvars()
