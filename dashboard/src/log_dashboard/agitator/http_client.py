"""HTTP client factory for Agitator scenarios.

Every Agitator-originated request MUST carry `X-Source: synthetic` so the
target app's request-logger tags the produced log line with that source
(ADR-011). Centralising the header here is the *only* enforcement point —
no scenario gets to forget it.
"""

from __future__ import annotations

import httpx

SYNTHETIC_SOURCE_HEADER = {"X-Source": "synthetic"}


def build_client(
    base_url: str,
    *,
    timeout: float = 10.0,
    extra_headers: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Return an `httpx.AsyncClient` pre-configured for an Agitator target.

    `X-Source: synthetic` is always set as a default header. `extra_headers`
    composes on top — used by `sda-degraded` to add `X-Chaos: slow:500`.
    `transport` is a test seam — pass `httpx.MockTransport(handler)` to
    intercept requests in unit tests; production callers leave it None.
    """
    headers = dict(SYNTHETIC_SOURCE_HEADER)
    if extra_headers:
        headers.update(extra_headers)
    kwargs: dict[str, object] = {
        "base_url": base_url,
        "timeout": timeout,
        "headers": headers,
    }
    if transport is not None:
        kwargs["transport"] = transport
    return httpx.AsyncClient(**kwargs)
