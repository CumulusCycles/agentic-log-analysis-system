"""Chaos middleware — header-driven failure simulation gated by ENABLE_CHAOS.

Behavior identical to the SDA chaos middleware (same directive grammar,
clamps, log events, response shape). Per ADR-013.

Stack position: registered BEFORE the request logger so chaos runs INSIDE
the logger (the request log line records the delayed/errored response).
FNOL has no api-key middleware — JWT is a route-level dependency — so
chaos and route dependencies execute in the same dispatch path.
"""

from __future__ import annotations

import asyncio

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import Settings
from ..logging_setup import get_logger

log = get_logger("chaos")

_MAX_SLOW_MS = 60_000


def _parse_directive(value: str) -> tuple[str, int] | None:
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
        log.warning(
            "chaos_honored",
            directive=directive,
            status=n,
            method=request.method,
            path=request.url.path,
        )
        return JSONResponse({"detail": "chaos"}, status_code=n)
