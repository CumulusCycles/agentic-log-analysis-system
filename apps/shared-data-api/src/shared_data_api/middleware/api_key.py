from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import Settings
from ..logging_setup import get_logger

log = get_logger("api_key")

# Only the Docker healthcheck endpoint is anonymous. /docs, /openapi.json, and
# /redoc require X-API-Key — the OpenAPI schema is sensitive surface area and
# leaving it unauthenticated leaks endpoint structure to anyone with network
# reach.
_PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})


class APIKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        named_keys: list[tuple[str, str]] = [
            ("fnol", settings.api_key_fnol),
            ("customer-portal", settings.api_key_customer_portal),
            ("agent-portal", settings.api_key_agent_portal),
        ]
        # Detect collisions before the dict comprehension silently drops them.
        seen: dict[str, str] = {}
        for app_name, key in named_keys:
            if key in seen:
                log.warning(
                    "api_key_collision",
                    apps=[seen[key], app_name],
                    message=(
                        "two SHARED_DATA_API_KEY_* env vars share the same value "
                        "— caller attribution will be ambiguous"
                    ),
                )
            else:
                seen[key] = app_name
        self._lookup: dict[str, str] = {key: app for app, key in named_keys}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            request.state.caller = "-"
            return await call_next(request)

        api_key = request.headers.get("x-api-key")
        if api_key is None:
            return JSONResponse(
                {"detail": "missing api key"},
                status_code=401,
            )
        caller = self._lookup.get(api_key)
        if caller is None:
            return JSONResponse(
                {"detail": "invalid api key"},
                status_code=401,
            )
        request.state.caller = caller
        return await call_next(request)
