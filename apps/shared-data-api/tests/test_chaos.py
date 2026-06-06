"""Chaos middleware — ENABLE_CHAOS env gate + X-Chaos directive grammar.

Covers the SDA ChaosMiddleware behavior contract (per ADR-013):
  - ENABLE_CHAOS=false  -> header ignored, normal request flow
  - ENABLE_CHAOS=true + slow:<ms>   -> sleep, then continue
  - ENABLE_CHAOS=true + error:<code> -> immediate response with that code
  - ENABLE_CHAOS=true + malformed   -> 400 + chaos_directive_invalid WARN
  - chaos_honored WARN fires with the expected fields

Tests assert on log shape (event + fields) using structlog capture; they
also confirm the handler did/didn't execute by checking the response body.
"""

from __future__ import annotations

import time

import pytest
import structlog
from httpx import ASGITransport, AsyncClient


def _build_app(monkeypatch, *, enable_chaos: bool):
    monkeypatch.setenv("ENABLE_CHAOS", "true" if enable_chaos else "false")
    from shared_data_api.config import get_settings
    from shared_data_api.main import create_app

    get_settings.cache_clear()
    return create_app()


async def _client(app):
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_chaos_disabled_ignores_header(monkeypatch, mongo_db, pg_session_factory):
    """ENABLE_CHAOS=false + X-Chaos header -> header ignored, handler runs."""
    app = _build_app(monkeypatch, enable_chaos=False)
    async with await _client(app) as client:
        resp = await client.get("/health", headers={"X-Chaos": "error:503"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_chaos_slow_delays_and_continues(monkeypatch, mongo_db, pg_session_factory):
    """slow:N sleeps for N ms, then forwards to the handler."""
    app = _build_app(monkeypatch, enable_chaos=True)
    async with await _client(app) as client:
        start = time.perf_counter()
        with structlog.testing.capture_logs() as captured:
            resp = await client.get("/health", headers={"X-Chaos": "slow:150"})
        elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    # Allow a small fudge factor for async scheduling.
    assert elapsed_ms >= 140, f"expected >= 140ms delay, got {elapsed_ms:.1f}ms"
    honored = [e for e in captured if e.get("event") == "chaos_honored"]
    assert len(honored) == 1
    assert honored[0]["log_level"] == "warning"
    assert honored[0]["directive"] == "slow:150"
    assert honored[0]["delay_ms"] == 150
    assert honored[0]["method"] == "GET"
    assert honored[0]["path"] == "/health"


@pytest.mark.asyncio
async def test_chaos_error_5xx_logs_at_error_level(monkeypatch, mongo_db, pg_session_factory):
    """error:<5xx> returns that status with detail=chaos, skips the handler,
    and logs `chaos_honored` at ERROR level so the dashboard's proactive
    scan (PR 4c) sees an ERROR-tier signal in Chroma."""
    app = _build_app(monkeypatch, enable_chaos=True)
    async with await _client(app) as client:
        with structlog.testing.capture_logs() as captured:
            resp = await client.get("/health", headers={"X-Chaos": "error:503"})
    assert resp.status_code == 503
    assert resp.json() == {"detail": "chaos"}
    honored = [e for e in captured if e.get("event") == "chaos_honored"]
    assert len(honored) == 1
    assert honored[0]["log_level"] == "error"
    assert honored[0]["status"] == 503
    assert honored[0]["directive"] == "error:503"


@pytest.mark.asyncio
async def test_chaos_error_4xx_logs_at_warning_level(monkeypatch, mongo_db, pg_session_factory):
    """error:<4xx> stays at WARN — a chaos-driven 418 is operator action,
    not a server failure. Keeps 4xx out of the ERROR-tier proactive scan
    signal."""
    app = _build_app(monkeypatch, enable_chaos=True)
    async with await _client(app) as client:
        with structlog.testing.capture_logs() as captured:
            resp = await client.get("/health", headers={"X-Chaos": "error:418"})
    assert resp.status_code == 418
    honored = [e for e in captured if e.get("event") == "chaos_honored"]
    assert len(honored) == 1
    assert honored[0]["log_level"] == "warning"
    assert honored[0]["status"] == 418


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "directive",
    [
        "garbage",
        "slow:abc",
        "slow:-1",
        "slow:60001",
        "error:399",
        "error:600",
        "unknown:200",
    ],
)
async def test_chaos_malformed_directive_returns_400(
    monkeypatch, mongo_db, pg_session_factory, directive
):
    """Malformed directive -> 400 with chaos_directive_invalid WARN."""
    app = _build_app(monkeypatch, enable_chaos=True)
    async with await _client(app) as client:
        with structlog.testing.capture_logs() as captured:
            resp = await client.get("/health", headers={"X-Chaos": directive})
    assert resp.status_code == 400
    assert "invalid X-Chaos directive" in resp.json()["detail"]
    rejected = [e for e in captured if e.get("event") == "chaos_directive_invalid"]
    assert len(rejected) == 1
    assert rejected[0]["log_level"] == "warning"
    assert rejected[0]["directive_raw"] == directive
    assert rejected[0]["reason"] == "malformed"


@pytest.mark.asyncio
async def test_chaos_no_header_passes_through(monkeypatch, mongo_db, pg_session_factory):
    """ENABLE_CHAOS=true but no X-Chaos header -> no chaos event, normal flow."""
    app = _build_app(monkeypatch, enable_chaos=True)
    async with await _client(app) as client:
        with structlog.testing.capture_logs() as captured:
            resp = await client.get("/health")
    assert resp.status_code == 200
    assert not any(e.get("event", "").startswith("chaos_") for e in captured)
