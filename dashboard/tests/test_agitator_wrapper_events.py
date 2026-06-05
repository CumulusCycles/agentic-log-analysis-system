"""Tests for the wrapper task's `agitator_run_started` and `agitator_run_complete` events.

The router's `_wrapped` coroutine emits these structured logs around the
scenario's `run()` call. Three terminal states must be exercised and
asserted to NOT carry any credential field — the events fan out to
stdout, can be ingested by the dashboard's own log pipeline, and could
end up in operator screenshots.
"""

from __future__ import annotations

import asyncio

import pytest
import structlog

from log_dashboard.agitator.auth import AppSession
from log_dashboard.agitator.scenarios import SCENARIOS

_FORBIDDEN = (
    "fake-fnol",  # the test JWT value
    "fake-cp",
    "fake-ap",
    "fake-api-key",
    "Authorization",
    "Bearer",
    "X-API-Key",
    "password",
)


def _fake_session() -> AppSession:
    return AppSession(
        fnol_jwt="fake-fnol",
        cp_jwt="fake-cp",
        ap_jwt="fake-ap",
        sda_customer_jwt="fake-cp",
        sda_api_key_cp="fake-api-key",
    )


def _assert_no_credentials(event: dict) -> None:
    flat = " ".join(repr(v) for v in event.values())
    for needle in _FORBIDDEN:
        assert needle not in flat, f"credential-shaped value {needle!r} leaked in {event!r}"


@pytest.fixture
def stub_bootstrap(monkeypatch: pytest.MonkeyPatch):
    from log_dashboard.routers import agitator as agitator_router

    async def _stub(settings):  # noqa: ANN001
        return _fake_session()

    monkeypatch.setattr(agitator_router, "bootstrap_session", _stub)


async def test_wrapper_emits_run_started_no_credentials(
    client, valid_token, stub_bootstrap, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`agitator_run_started` fires on every successful run launch."""

    async def _noop(self) -> None:
        return

    monkeypatch.setattr(SCENARIOS["auth-spike"], "run", _noop)

    with structlog.testing.capture_logs() as logs:
        response = await client.post(
            "/api/agitator/runs",
            json={"scenario": "auth-spike"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 201
        await asyncio.sleep(0.05)

    started = [e for e in logs if e.get("event") == "agitator_run_started"]
    assert len(started) == 1
    assert started[0]["scenario"] == "auth-spike"
    assert "run_id" in started[0]
    _assert_no_credentials(started[0])


async def test_wrapper_emits_complete_succeeded_no_credentials(
    client, valid_token, stub_bootstrap, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Success path: `agitator_run_complete` with state=succeeded."""

    async def _noop(self) -> None:
        return

    monkeypatch.setattr(SCENARIOS["auth-spike"], "run", _noop)

    with structlog.testing.capture_logs() as logs:
        await client.post(
            "/api/agitator/runs",
            json={"scenario": "auth-spike"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        await asyncio.sleep(0.1)

    complete = [e for e in logs if e.get("event") == "agitator_run_complete"]
    assert len(complete) == 1
    assert complete[0]["state"] == "succeeded"
    assert complete[0]["scenario"] == "auth-spike"
    _assert_no_credentials(complete[0])


async def test_wrapper_emits_complete_failed_no_credentials(
    client, valid_token, stub_bootstrap, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed path: `agitator_run_complete` with state=failed + error_class.

    The full exception message is sanitised via `_sanitize_error` BEFORE
    landing on `last_error`; the event itself only carries `error_class`.
    """

    async def _boom(self) -> None:
        raise RuntimeError("synthetic scenario failure")

    monkeypatch.setattr(SCENARIOS["auth-spike"], "run", _boom)

    with structlog.testing.capture_logs() as logs:
        await client.post(
            "/api/agitator/runs",
            json={"scenario": "auth-spike"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        await asyncio.sleep(0.1)

    complete = [e for e in logs if e.get("event") == "agitator_run_complete"]
    assert len(complete) == 1
    assert complete[0]["state"] == "failed"
    assert complete[0]["error_class"] == "RuntimeError"
    # Error MESSAGE must not be in the event — only the class name.
    flat = " ".join(repr(v) for v in complete[0].values())
    assert "synthetic scenario failure" not in flat
    _assert_no_credentials(complete[0])


async def test_wrapper_emits_complete_cancelled_no_credentials(
    client, valid_token, stub_bootstrap, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancelled path: `agitator_run_complete` with state=cancelled."""
    cancel_observed = asyncio.Event()

    async def _slow(self) -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancel_observed.set()
            raise

    monkeypatch.setattr(SCENARIOS["auth-spike"], "run", _slow)

    with structlog.testing.capture_logs() as logs:
        start = await client.post(
            "/api/agitator/runs",
            json={"scenario": "auth-spike"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        run_id = start.json()["run_id"]
        await client.post(
            f"/api/agitator/runs/{run_id}/cancel",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        await asyncio.wait_for(cancel_observed.wait(), timeout=2.0)
        # Let the wrapper coroutine finalize.
        await asyncio.sleep(0.05)

    complete = [e for e in logs if e.get("event") == "agitator_run_complete"]
    assert len(complete) == 1
    assert complete[0]["state"] == "cancelled"
    _assert_no_credentials(complete[0])
