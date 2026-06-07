"""SDA: `X-Source` header is bound onto structlog contextvars so domain
events emitted during the request inherit `source` via `merge_contextvars`.

These tests target the contextvar binding directly — `capture_logs` runs
before the processor chain, so the test exercises the contextvar API
that `merge_contextvars` reads at production processor-runtime.
"""

from __future__ import annotations

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shared_data_api.logging_setup import configure_logging
from shared_data_api.middleware.request_logger import (
    RequestLoggerMiddleware,
    _normalize_source,
)


@pytest.fixture(autouse=True)
def _setup_logging():
    configure_logging(log_file_path="/tmp/sda-test-source-propagation.log")
    yield
    structlog.contextvars.clear_contextvars()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("synthetic", "synthetic"),
        ("Synthetic", "synthetic"),
        ("  test  ", "test"),
        ("PROD", "prod"),
        # Missing / blank header → `unknown` per ADR-011 2026-06-07 amendment.
        # Real UX traffic must tag `prod` explicitly from the React SPA.
        (None, "unknown"),
        ("", "unknown"),
        ("   ", "unknown"),
    ],
)
def test_normalize_source(raw, expected) -> None:
    assert _normalize_source(raw) == expected


@pytest.mark.asyncio
async def test_request_binds_source_into_structlog_contextvars() -> None:
    """While the request handler runs, `structlog.contextvars` carries the
    source bound by the middleware. After the response, it's cleared."""
    bound_during_request: dict = {}

    async def _probe_route():
        # Read the contextvars dict from inside the request — production
        # domain loggers see this same dict through `merge_contextvars`.
        bound_during_request.update(structlog.contextvars.get_contextvars())
        return {"ok": True}

    app = FastAPI()
    app.add_middleware(RequestLoggerMiddleware)
    app.get("/probe")(_probe_route)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/probe", headers={"X-Source": "synthetic"})
    assert resp.status_code == 200
    assert bound_during_request.get("source") == "synthetic"
    # And the middleware cleared the contextvars after dispatch.
    assert structlog.contextvars.get_contextvars().get("source") is None


@pytest.mark.asyncio
async def test_request_default_source_when_header_missing() -> None:
    """Header-absent request → `source=unknown` per ADR-011 2026-06-07
    amendment. Real UX traffic tags `prod` explicitly from the SPA; missing
    header is the leak-detection signal."""
    bound: dict = {}

    async def _probe():
        bound.update(structlog.contextvars.get_contextvars())
        return {"ok": True}

    app = FastAPI()
    app.add_middleware(RequestLoggerMiddleware)
    app.get("/probe")(_probe)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.get("/probe")
    assert bound.get("source") == "unknown"


@pytest.mark.asyncio
async def test_contextvars_dont_leak_across_requests() -> None:
    """Second request must not see the source from the first.

    Without `clear_contextvars()` at the start of dispatch, the prior
    request's `source` could leak into a fresh request that omits
    `X-Source`. This regression-locks that defence.
    """
    sources_seen: list[str] = []

    async def _probe():
        sources_seen.append(structlog.contextvars.get_contextvars().get("source", "<missing>"))
        return {"ok": True}

    app = FastAPI()
    app.add_middleware(RequestLoggerMiddleware)
    app.get("/probe")(_probe)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.get("/probe", headers={"X-Source": "synthetic"})
        await ac.get("/probe")  # no header

    assert sources_seen == ["synthetic", "unknown"]
