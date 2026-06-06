"""Chaos middleware — header-driven failure simulation gated by ENABLE_CHAOS.

When ENABLE_CHAOS=false (the default and production posture), the middleware
short-circuits to a no-op regardless of the header. When ENABLE_CHAOS=true,
the middleware reads an optional ``X-Chaos: <directive>`` header on each
request and simulates the requested failure:

  X-Chaos: slow:<ms>      -- sleep N ms (0..60000), then continue normally
  X-Chaos: error:<status> -- return immediate HTTP <status> (400..599)

Malformed directives are rejected with 400 and a ``chaos_directive_invalid``
WARN log; honored directives emit a ``chaos_honored`` WARN log so the
dashboard sees chaos events as part of the corpus (PR 4 LangGraph will
need them to recognize induced cascades).

Stack position: registered BEFORE the API-key middleware (so APIKey wraps
chaos, i.e. chaos runs AFTER auth). Unauthenticated requests with X-Chaos
are rejected by APIKey at 401 before chaos sees them — chaos cannot bypass
security.

Per ADR-013.
"""

from __future__ import annotations

import asyncio

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import Settings
from ..logging_setup import get_logger

log = get_logger("chaos")

_MAX_SLOW_MS = 60_000


def _parse_directive(value: str) -> tuple[str, int] | None:
    """Parse `slow:<n>` or `error:<n>`. Returns (kind, n) or None on rejection."""
    if ":" not in value:
        return None
    kind, raw = value.split(":", 1)
    try:
        n = int(raw)
    except ValueError:
        return None
    if kind == "slow" and 0 <= n <= _MAX_SLOW_MS:
        return ("slow", n)
    if kind == "error" and 400 <= n <= 599:
        return ("error", n)
    return None


class ChaosMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self._enabled = settings.enable_chaos

    async def dispatch(self, request: Request, call_next):
        if not self._enabled:
            return await call_next(request)
        directive = request.headers.get("X-Chaos")
        if not directive:
            return await call_next(request)
        parsed = _parse_directive(directive)
        if parsed is None:
            log.warning(
                "chaos_directive_invalid",
                directive_raw=directive,
                reason="malformed",
                method=request.method,
                path=request.url.path,
            )
            return JSONResponse(
                {"detail": f"invalid X-Chaos directive: {directive}"},
                status_code=400,
            )
        kind, n = parsed
        if kind == "slow":
            await asyncio.sleep(n / 1000)
            log.warning(
                "chaos_honored",
                directive=directive,
                delay_ms=n,
                method=request.method,
                path=request.url.path,
            )
            return await call_next(request)
        # kind == "error" — split level by status class so 5xx is ERROR-tier
        # signal in Chroma (PR 4c proactive scan needs it). 4xx stays WARN:
        # a chaos-driven 418 is operator action, not a server failure.
        log_method = log.error if 500 <= n <= 599 else log.warning
        log_method(
            "chaos_honored",
            directive=directive,
            status=n,
            method=request.method,
            path=request.url.path,
        )
        return JSONResponse({"detail": "chaos"}, status_code=n)
