"""FNOL: `X-Source` propagation — binds onto structlog contextvars (so
domain events inherit it) AND is forwarded by the outbound SdaClient on
every call to SDA. Without the forward, SDA would only ever see source=prod
from FNOL's traffic, defeating the cross-app propagation chain.
"""

from __future__ import annotations

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fnol.logging_setup import configure_logging
from fnol.middleware.request_logger import RequestLoggerMiddleware


@pytest.fixture(autouse=True)
def _setup_logging():
    configure_logging(log_file_path="/tmp/fnol-test-source-propagation.log")
    yield
    structlog.contextvars.clear_contextvars()


@pytest.mark.asyncio
async def test_request_binds_source_into_contextvars() -> None:
    bound: dict = {}

    async def _probe():
        bound.update(structlog.contextvars.get_contextvars())
        return {"ok": True}

    app = FastAPI()
    app.add_middleware(RequestLoggerMiddleware)
    app.get("/probe")(_probe)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.get("/probe", headers={"X-Source": "test"})

    assert bound.get("source") == "test"


def test_current_source_falls_back_to_prod_outside_request() -> None:
    """When no contextvar is bound (e.g. process startup), the SdaClient
    helper falls back to `prod` rather than raising."""
    structlog.contextvars.clear_contextvars()
    from fnol.clients.shared_data_api import _current_source

    assert _current_source() == "prod"


def test_current_source_reads_bound_contextvar() -> None:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(source="synthetic")
    try:
        from fnol.clients.shared_data_api import _current_source

        assert _current_source() == "synthetic"
    finally:
        structlog.contextvars.clear_contextvars()


@pytest.mark.asyncio
async def test_sda_client_forwards_x_source_header(monkeypatch) -> None:
    """Outbound calls to SDA must carry `X-Source: <current source>` so
    SDA's middleware tags the inbound request with the same source. The
    Agitator → FNOL → SDA chain depends on this forward.
    """
    from fnol.clients.shared_data_api import SharedDataAPIClient
    from fnol.config import get_settings

    captured_headers: list[dict] = []

    class _StubAsyncClient:
        async def post(self, target, json=None, headers=None):
            captured_headers.append(dict(headers or {}))

            class _Resp:
                status_code = 200

                def raise_for_status(self):
                    pass

                def json(self):
                    return {"ok": True}

            return _Resp()

        async def get(self, target, headers=None):
            return await self.post(target, headers=headers)

        async def aclose(self):
            pass

    settings = get_settings()
    client = SharedDataAPIClient(settings)
    # Replace the live httpx client with our stub so no network is touched.
    object.__setattr__(client, "_client", _StubAsyncClient())

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(source="synthetic")
    try:
        await client.login("alice", "irrelevant")
        await client.create_claim({"foo": "bar"}, bearer="t")
        await client.get_claim("c1", bearer="t")
    finally:
        structlog.contextvars.clear_contextvars()

    assert len(captured_headers) == 3
    for headers in captured_headers:
        assert headers.get("X-Source") == "synthetic"
