"""v1.1.2 Option A — embeddings-promotion watchdog tests.

The watchdog (`_await_embeddings_then_backfill` in `main.py`) is the core
v1.1.2 cold-deploy mechanism. It polls `embeddings_state` on a configurable
interval until the probe flips from `"loading"` to `"ready"`, then wires up
the vectorstore + rebuilds the agent graph + kicks off backfill.

These tests drive the lifespan with a scripted `embeddings_state` mock so
the state transition happens deterministically without real network or
real Ollama. The watchdog's promotion interval is forced to a sub-second
value via env so the loop runs end-to-end in test time.
"""

from __future__ import annotations

import asyncio
import itertools

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from log_dashboard.config import get_settings


def _state_sequence(*states: str):
    """Return a callable that yields each state in turn, then sticks on the
    last value. The mock must be deterministic across the unknown number
    of probe calls the watchdog makes."""
    seq = iter(itertools.chain(states, itertools.repeat(states[-1])))
    return lambda _settings: next(seq)


@pytest_asyncio.fixture
async def promotion_app(monkeypatch, fake_vectorstore):
    """Lifespan with: probe returns `loading` first, then `ready`; a fake
    vectorstore is wired on promotion; backfill is a no-op stub so the
    test doesn't wait on real Chroma writes.
    """
    monkeypatch.setenv("DASHBOARD_EMBEDDINGS_PROMOTION_INTERVAL_SECONDS", "5")
    get_settings.cache_clear()

    from log_dashboard import main as main_module

    monkeypatch.setattr(main_module, "embeddings_state", _state_sequence("loading", "ready"))
    monkeypatch.setattr(main_module, "build_vectorstore", lambda _s, **_kw: fake_vectorstore)
    monkeypatch.setattr(main_module, "run_initial_backfill", lambda *_a, **_kw: [])

    from log_dashboard.main import create_app

    app = create_app()
    async with LifespanManager(app):
        yield app


@pytest_asyncio.fixture
async def loading_only_app(monkeypatch):
    """Lifespan with a probe that stays in `loading` forever — used to
    assert the watchdog is started and `embeddings_state` reports the
    loading value, without driving a promotion."""
    monkeypatch.setenv("DASHBOARD_EMBEDDINGS_PROMOTION_INTERVAL_SECONDS", "5")
    get_settings.cache_clear()

    from log_dashboard import main as main_module

    monkeypatch.setattr(main_module, "embeddings_state", lambda _s: "loading")
    # build_vectorstore would not be called in pure loading state, but
    # patch it to a no-op so a future bug doesn't try to call it.
    monkeypatch.setattr(main_module, "build_vectorstore", lambda _s, **_kw: None)
    monkeypatch.setattr(main_module, "run_initial_backfill", lambda *_a, **_kw: [])

    from log_dashboard.main import create_app

    app = create_app()
    async with LifespanManager(app):
        yield app


@pytest.mark.asyncio
async def test_lifespan_loading_state_writes_app_state(loading_only_app) -> None:
    """When the initial probe reports `loading`, lifespan writes
    `embeddings_state="loading"` on app.state so /api/status surfaces it.
    """
    assert loading_only_app.state.embeddings_state == "loading"
    # backfill_complete stays False — the watchdog will flip it once the
    # vectorstore is wired and backfill runs.
    assert loading_only_app.state.backfill_complete is False
    # Vectorstore is None — Search router 503s with the "warming up" detail.
    assert loading_only_app.state.vectorstore is None


@pytest.mark.asyncio
async def test_watchdog_promotes_loading_to_ready_and_wires_vectorstore(
    promotion_app, fake_vectorstore
) -> None:
    """The watchdog detects the `loading → ready` transition, builds the
    vectorstore, rebuilds the agent graph against the live store, and
    kicks off backfill — without operator intervention.

    Round-4 fix: the watchdog writes `embeddings_state="ready"` LAST
    (after vectorstore + graph are wired). This test pins that ordering
    by checking, after promotion, that both the state AND the live
    references are present together.
    """
    # Initial probe returned "loading" → watchdog scheduled. Allow it to
    # tick at least twice (sleep > interval) so the second probe reports
    # "ready" and the promotion sequence completes.
    await asyncio.sleep(12)

    assert promotion_app.state.embeddings_state == "ready"
    # Compound state must be coherent — round-4 fix prevents the
    # ready-but-vectorstore-is-None window.
    assert promotion_app.state.vectorstore is fake_vectorstore
    assert promotion_app.state.agent_graph is not None
    # Backfill ran as part of promotion (stubbed to a no-op).
    assert promotion_app.state.backfill_complete is True


@pytest.mark.asyncio
async def test_watchdog_preserves_agent_checkpointer_across_rebuild(
    promotion_app,
) -> None:
    """Promotion rebuilds the agent graph but MUST reuse the same
    checkpointer so any in-flight conversations' thread state survives.
    """
    pre_promotion_checkpointer = promotion_app.state.agent_checkpointer
    await asyncio.sleep(12)

    # Same object — not a fresh InMemorySaver.
    assert promotion_app.state.agent_checkpointer is pre_promotion_checkpointer
    # Session index still references the same checkpointer too.
    assert promotion_app.state.session_index._checkpointer is pre_promotion_checkpointer


@pytest.mark.asyncio
async def test_status_endpoint_surfaces_loading_state(loading_only_app, valid_token) -> None:
    """/api/status carries `embeddings_state` so the frontend can show a
    friendlier hint during the cold-deploy window. Pin the `loading`
    value flowing through the response.
    """
    transport = ASGITransport(app=loading_only_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/status", headers={"Authorization": f"Bearer {valid_token}"})
    assert response.status_code == 200
    assert response.json()["embeddings_state"] == "loading"


@pytest.mark.asyncio
async def test_status_endpoint_surfaces_ready_state_after_promotion(
    promotion_app, valid_token
) -> None:
    """After watchdog promotion, /api/status reports `embeddings_state="ready"`
    — closes the round-4 coverage gap on the field round-trip.
    """
    await asyncio.sleep(12)

    transport = ASGITransport(app=promotion_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/status", headers={"Authorization": f"Bearer {valid_token}"})
    assert response.status_code == 200
    assert response.json()["embeddings_state"] == "ready"


@pytest.mark.asyncio
async def test_status_endpoint_surfaces_unreachable_state(monkeypatch, valid_token) -> None:
    """When the initial probe reports `unreachable`, lifespan writes that
    value and /api/status surfaces it. No watchdog runs (an unreachable
    URL won't self-heal)."""
    monkeypatch.setenv("DASHBOARD_EMBEDDINGS_PROMOTION_INTERVAL_SECONDS", "5")
    get_settings.cache_clear()

    from log_dashboard import main as main_module

    monkeypatch.setattr(main_module, "embeddings_state", lambda _s: "unreachable")

    from log_dashboard.main import create_app

    app = create_app()
    async with LifespanManager(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/status", headers={"Authorization": f"Bearer {valid_token}"}
            )
        assert response.status_code == 200
        assert response.json()["embeddings_state"] == "unreachable"
