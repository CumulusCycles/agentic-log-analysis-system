"""Thin async HTTP client around the Shared Data API.

Holds a single `httpx.AsyncClient` for the lifetime of the FNOL app. The
`X-API-Key` header is set once at construction so every outgoing request
includes it — per ADR-006 §1 the key is required on every SDA call,
including `/auth/login`.

Every outbound call logs `sda_upstream_rejected` (WARN) on 4xx/5xx or
`sda_upstream_unreachable` (WARN) on a transport error, then re-raises so
the existing router-level error translation continues to work. The log
events emit the `target` path, response `status`, and parsed `detail` —
NEVER the bearer header, NEVER the API key, NEVER the password.
"""

import httpx
import structlog

from ..config import Settings
from ..logging_setup import get_logger

log = get_logger("sda_client")


def _current_source() -> str:
    """Pull `source` from the structlog contextvars set by the request
    middleware. Defaults to `unknown` if FNOL emits an outbound call outside
    a request context (startup probes, background tasks). Real UX traffic
    arrives with `X-Source: prod` from the React SPA and propagates through
    the contextvar; the `unknown` fallback is the leak-detection signal per
    ADR-011 2026-06-07 amendment."""
    return str(structlog.contextvars.get_contextvars().get("source") or "unknown")


def _detail_from(resp: httpx.Response) -> str:
    """Best-effort extraction of `detail` from an SDA error response body.

    Returns a generic "upstream error" string on any parse failure. NEVER
    serializes the response headers (would leak API key / Authorization).
    """
    try:
        return str(resp.json().get("detail", "upstream error"))
    except (ValueError, AttributeError):
        return "upstream error"


class SharedDataAPIClient:
    def __init__(self, settings: Settings, *, timeout: float = 10.0):
        self._client = httpx.AsyncClient(
            base_url=settings.shared_data_api_base_url,
            timeout=timeout,
            headers={"X-API-Key": settings.shared_data_api_key_fnol},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def login(self, username: str, password: str) -> dict:
        target = "/auth/login"
        try:
            r = await self._client.post(
                target,
                json={"username": username, "password": password},
                headers={"X-Source": _current_source()},
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.warning(
                "sda_upstream_rejected",
                target=target,
                status=exc.response.status_code,
                detail=_detail_from(exc.response),
            )
            raise
        except httpx.RequestError as exc:
            log.warning(
                "sda_upstream_unreachable",
                target=target,
                error_class=type(exc).__name__,
            )
            raise
        return r.json()

    async def create_claim(self, payload: dict, bearer: str) -> dict:
        target = "/claims"
        try:
            r = await self._client.post(
                target,
                json=payload,
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "X-Source": _current_source(),
                },
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.warning(
                "sda_upstream_rejected",
                target=target,
                status=exc.response.status_code,
                detail=_detail_from(exc.response),
            )
            raise
        except httpx.RequestError as exc:
            log.warning(
                "sda_upstream_unreachable",
                target=target,
                error_class=type(exc).__name__,
            )
            raise
        return r.json()

    async def get_claim(self, claim_id: str, bearer: str) -> dict:
        target = f"/claims/{claim_id}"
        try:
            r = await self._client.get(
                target,
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "X-Source": _current_source(),
                },
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.warning(
                "sda_upstream_rejected",
                target=target,
                status=exc.response.status_code,
                detail=_detail_from(exc.response),
            )
            raise
        except httpx.RequestError as exc:
            log.warning(
                "sda_upstream_unreachable",
                target=target,
                error_class=type(exc).__name__,
            )
            raise
        return r.json()
