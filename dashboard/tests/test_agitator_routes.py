"""Tests for /api/agitator/* — endpoint contracts.

Each test stubs `bootstrap_session` so the route logic exercises without
hitting any of the four target apps. Scenario `run()` is also stubbed
where the test only cares about the route, not the work.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from log_dashboard.agitator.auth import AppSession
from log_dashboard.agitator.runs import RunRecord, RunRegistry


def _fake_session() -> AppSession:
    return AppSession(
        fnol_jwt="fake-fnol",
        cp_jwt="fake-cp",
        ap_jwt="fake-ap",
        sda_customer_jwt="fake-cp",
        sda_api_key_cp="fake-api-key",
    )


@pytest.fixture
def stub_bootstrap(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Stub bootstrap_session to skip real logins."""
    from log_dashboard.routers import agitator as agitator_router

    async def _stub(settings):  # noqa: ANN001 — signature matches real impl
        return _fake_session()

    monkeypatch.setattr(agitator_router, "bootstrap_session", _stub)
    yield


@pytest.fixture
def stub_scenarios(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Replace each scenario's run() with a tiny no-op that increments sent
    once so the registry shows non-zero progress. Avoids any HTTP traffic."""
    from log_dashboard.agitator.scenarios import SCENARIOS

    for cls in SCENARIOS.values():

        async def _run(self):  # noqa: ANN001 — bound to cls below
            await self.registry.mark_sent(self.run_id, 200, ok=True)

        monkeypatch.setattr(cls, "run", _run)
    yield


async def test_routes_require_admin_jwt(client) -> None:
    for path in (
        "/api/agitator/scenarios",
        "/api/agitator/env",
        "/api/agitator/runs",
    ):
        response = await client.get(path)
        assert response.status_code == 401, path

    response = await client.post("/api/agitator/runs", json={"scenario": "auth-spike"})
    assert response.status_code == 401


async def test_list_scenarios_returns_five_specs(client, valid_token) -> None:
    response = await client.get(
        "/api/agitator/scenarios",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    names = {s["name"] for s in body}
    assert names == {
        "auth-spike",
        "payload-fuzz",
        "policy-not-found",
        "claim-burst",
        "sda-degraded",
    }
    sda = next(s for s in body if s["name"] == "sda-degraded")
    assert sda["requires_chaos"] is True
    others = [s for s in body if s["name"] != "sda-degraded"]
    assert all(s["requires_chaos"] is False for s in others)


async def test_env_reports_enable_chaos(client, valid_token) -> None:
    response = await client.get(
        "/api/agitator/env",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"enable_chaos": False}


async def test_start_unknown_scenario_returns_404(client, valid_token, stub_bootstrap) -> None:
    response = await client.post(
        "/api/agitator/runs",
        json={"scenario": "made-up"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 404


async def test_start_sda_degraded_when_chaos_disabled_returns_409(
    client, valid_token, stub_bootstrap
) -> None:
    response = await client.post(
        "/api/agitator/runs",
        json={"scenario": "sda-degraded"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 409
    assert "ENABLE_CHAOS" in response.json()["detail"]


async def test_start_run_returns_running_state(
    client, valid_token, stub_bootstrap, stub_scenarios
) -> None:
    response = await client.post(
        "/api/agitator/runs",
        json={"scenario": "auth-spike"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["scenario"] == "auth-spike"
    assert body["state"] in ("running", "succeeded")  # stub may finish before response
    assert body["params"] == {"count": 50, "duration_s": 30}
    assert body["run_id"]


async def test_get_run_returns_counters(
    client, valid_token, stub_bootstrap, stub_scenarios
) -> None:
    start = await client.post(
        "/api/agitator/runs",
        json={"scenario": "auth-spike"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    run_id = start.json()["run_id"]
    # Stub increments sent once then exits. Let the wrapper finalise.
    await asyncio.sleep(0.05)

    response = await client.get(
        f"/api/agitator/runs/{run_id}",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["sent"] >= 1
    assert body["state"] in ("running", "succeeded")


async def test_get_unknown_run_returns_404(client, valid_token) -> None:
    response = await client.get(
        "/api/agitator/runs/does-not-exist",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 404


async def test_list_runs_returns_recent(
    client, valid_token, stub_bootstrap, stub_scenarios
) -> None:
    await client.post(
        "/api/agitator/runs",
        json={"scenario": "auth-spike"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    await asyncio.sleep(0.05)
    await client.post(
        "/api/agitator/runs",
        json={"scenario": "payload-fuzz"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    await asyncio.sleep(0.05)
    response = await client.get(
        "/api/agitator/runs",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    runs = response.json()["runs"]
    assert len(runs) == 2
    scenarios = {r["scenario"] for r in runs}
    assert scenarios == {"auth-spike", "payload-fuzz"}


async def test_param_out_of_range_returns_422(client, valid_token, stub_bootstrap) -> None:
    response = await client.post(
        "/api/agitator/runs",
        json={"scenario": "auth-spike", "params": {"count": 99999}},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 422


async def test_unknown_param_returns_422(client, valid_token, stub_bootstrap) -> None:
    response = await client.post(
        "/api/agitator/runs",
        json={"scenario": "auth-spike", "params": {"bogus": 1}},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 422


async def test_cancel_unknown_run_returns_404(client, valid_token) -> None:
    response = await client.post(
        "/api/agitator/runs/no-such-id/cancel",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 404


async def test_cancel_running_run_marks_cancelled(client, valid_token) -> None:
    """Drive a long-running scenario, cancel mid-flight, verify state flip."""
    from log_dashboard.routers import agitator as agitator_router

    cancel_event = asyncio.Event()

    async def _slow_session(settings):  # noqa: ANN001
        return _fake_session()

    # Pin to a scenario that yields control so cancel can land.
    from log_dashboard.agitator.scenarios import SCENARIOS

    class _SlowScenario(SCENARIOS["auth-spike"]):  # type: ignore[misc, valid-type]
        async def run(self) -> None:
            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=5.0)
            except TimeoutError:
                pass

    original_cls = SCENARIOS["auth-spike"]
    SCENARIOS["auth-spike"] = _SlowScenario
    try:
        # Patch bootstrap via monkeypatch shadow on the router.
        agitator_router.bootstrap_session = _slow_session  # type: ignore[assignment]

        start = await client.post(
            "/api/agitator/runs",
            json={"scenario": "auth-spike"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        run_id = start.json()["run_id"]

        cancel = await client.post(
            f"/api/agitator/runs/{run_id}/cancel",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert cancel.status_code == 200
        # Allow the wrapper coroutine to observe the cancel.
        await asyncio.sleep(0.1)

        final = await client.get(
            f"/api/agitator/runs/{run_id}",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert final.json()["state"] == "cancelled"
    finally:
        SCENARIOS["auth-spike"] = original_cls
        # Restore the original bootstrap reference.
        from log_dashboard.agitator.auth import bootstrap_session as real_bootstrap

        agitator_router.bootstrap_session = real_bootstrap  # type: ignore[assignment]


async def test_bootstrap_failure_returns_502(
    client, valid_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    from log_dashboard.agitator.auth import AgitatorAuthError
    from log_dashboard.routers import agitator as agitator_router

    async def _boom(settings):  # noqa: ANN001
        raise AgitatorAuthError("upstream unreachable")

    monkeypatch.setattr(agitator_router, "bootstrap_session", _boom)
    response = await client.post(
        "/api/agitator/runs",
        json={"scenario": "auth-spike"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 502
    assert "upstream unreachable" in response.json()["detail"]


async def test_registry_max_recent_evicts_oldest_non_running(client) -> None:
    """Unit-level check on the registry's eviction rule.

    Lives in the routes file because it touches the same infrastructure;
    keeps the run_count low.
    """
    registry = RunRegistry(max_recent=3)
    now = datetime.now(tz=UTC)
    for i in range(5):
        record = RunRecord(
            run_id=f"r{i}",
            scenario_name="auth-spike",
            params={},
            started_at=now,
            state="succeeded",
        )
        await registry.add(record)
    recent = await registry.list_recent()
    assert len(recent) == 3
    # Last three should be r2, r3, r4 (oldest evicted).
    assert [r.run_id for r in recent] == ["r2", "r3", "r4"]
