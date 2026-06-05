"""Chaos middleware — ENABLE_CHAOS env gate + X-Chaos directive grammar.

Covers the FNOL ChaosMiddleware behavior contract (per ADR-013).
"""

from __future__ import annotations

import time

import pytest
import structlog
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient


async def _make_client(monkeypatch, *, enable_chaos: bool):
    monkeypatch.setenv("ENABLE_CHAOS", "true" if enable_chaos else "false")
    from fnol.config import get_settings
    from fnol.main import create_app

    get_settings.cache_clear()
    app = create_app()
    manager = LifespanManager(app)
    await manager.__aenter__()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    return client, manager


@pytest.mark.asyncio
async def test_chaos_disabled_ignores_header(monkeypatch):
    client, manager = await _make_client(monkeypatch, enable_chaos=False)
    try:
        resp = await client.get("/health", headers={"X-Chaos": "error:503"})
        assert resp.status_code == 200
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_chaos_slow_delays_and_continues(monkeypatch):
    client, manager = await _make_client(monkeypatch, enable_chaos=True)
    try:
        start = time.perf_counter()
        with structlog.testing.capture_logs() as captured:
            resp = await client.get("/health", headers={"X-Chaos": "slow:120"})
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert resp.status_code == 200
        assert elapsed_ms >= 110, f"expected >= 110ms delay, got {elapsed_ms:.1f}ms"
        honored = [e for e in captured if e.get("event") == "chaos_honored"]
        assert len(honored) == 1
        assert honored[0]["log_level"] == "warning"
        assert honored[0]["delay_ms"] == 120
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_chaos_error_returns_status(monkeypatch):
    client, manager = await _make_client(monkeypatch, enable_chaos=True)
    try:
        with structlog.testing.capture_logs() as captured:
            resp = await client.get("/health", headers={"X-Chaos": "error:502"})
        assert resp.status_code == 502
        assert resp.json() == {"detail": "chaos"}
        honored = [e for e in captured if e.get("event") == "chaos_honored"]
        assert len(honored) == 1
        assert honored[0]["status"] == 502
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_chaos_malformed_directive_returns_400(monkeypatch):
    client, manager = await _make_client(monkeypatch, enable_chaos=True)
    try:
        with structlog.testing.capture_logs() as captured:
            resp = await client.get("/health", headers={"X-Chaos": "garbage"})
        assert resp.status_code == 400
        rejected = [e for e in captured if e.get("event") == "chaos_directive_invalid"]
        assert len(rejected) == 1
        assert rejected[0]["log_level"] == "warning"
        assert rejected[0]["directive_raw"] == "garbage"
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_chaos_no_header_passes_through(monkeypatch):
    client, manager = await _make_client(monkeypatch, enable_chaos=True)
    try:
        with structlog.testing.capture_logs() as captured:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert not any(e.get("event", "").startswith("chaos_") for e in captured)
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)
