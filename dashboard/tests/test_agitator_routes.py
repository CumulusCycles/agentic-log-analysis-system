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


async def test_list_scenarios_returns_all_specs(client, valid_token) -> None:
    response = await client.get(
        "/api/agitator/scenarios",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    names = {s["name"] for s in body}
    # 6 originals + 4 CP/AP scenarios = 10 total, covering every target app.
    assert names == {
        "auth-spike",
        "payload-fuzz",
        "policy-not-found",
        "claim-burst",
        "sda-degraded",
        "error-burst",
        "cp-read-burst",
        "cp-degraded",
        "ap-read-burst",
        "ap-degraded",
    }
    # The four `*-degraded` + `error-burst` scenarios require ENABLE_CHAOS=true;
    # the rest don't.
    chaos_names = {"sda-degraded", "error-burst", "cp-degraded", "ap-degraded"}
    for spec in body:
        if spec["name"] in chaos_names:
            assert spec["requires_chaos"] is True, spec["name"]
        else:
            assert spec["requires_chaos"] is False, spec["name"]
    # Every target app is represented.
    target_apps = {s["target_app"] for s in body}
    assert target_apps == {
        "shared-data-api",
        "fnol",
        "customer-portal",
        "agent-portal",
    }


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


async def test_start_error_burst_when_chaos_disabled_returns_409(
    client, valid_token, stub_bootstrap
) -> None:
    """PR 4c: error-burst is the second chaos-gated scenario. Same 409
    contract as sda-degraded when ENABLE_CHAOS=false."""
    response = await client.post(
        "/api/agitator/runs",
        json={"scenario": "error-burst"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 409
    assert "ENABLE_CHAOS" in response.json()["detail"]


async def test_start_cp_degraded_when_chaos_disabled_returns_409(
    client, valid_token, stub_bootstrap
) -> None:
    """cp-degraded requires ENABLE_CHAOS=true; the router returns 409 otherwise."""
    response = await client.post(
        "/api/agitator/runs",
        json={"scenario": "cp-degraded"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 409
    assert "ENABLE_CHAOS" in response.json()["detail"]


async def test_start_ap_degraded_when_chaos_disabled_returns_409(
    client, valid_token, stub_bootstrap
) -> None:
    """ap-degraded requires ENABLE_CHAOS=true; the router returns 409 otherwise."""
    response = await client.post(
        "/api/agitator/runs",
        json={"scenario": "ap-degraded"},
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


async def test_cancel_running_run_marks_cancelled(
    client, valid_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cancel mid-flight → scenario sees CancelledError → registry flips to cancelled.

    Uses monkeypatch.setitem / setattr so pytest handles teardown. Asserts
    via an asyncio.Event that the scenario's run() coroutine actually
    observed CancelledError — without that, a green test could mask a
    silent task leak.
    """
    from log_dashboard.agitator.scenarios import SCENARIOS
    from log_dashboard.routers import agitator as agitator_router

    cancel_observed = asyncio.Event()

    async def _stub_bootstrap(settings):  # noqa: ANN001
        return _fake_session()

    class _SlowScenario(SCENARIOS["auth-spike"]):  # type: ignore[misc, valid-type]
        async def run(self) -> None:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancel_observed.set()
                raise

    monkeypatch.setitem(SCENARIOS, "auth-spike", _SlowScenario)
    monkeypatch.setattr(agitator_router, "bootstrap_session", _stub_bootstrap)

    start = await client.post(
        "/api/agitator/runs",
        json={"scenario": "auth-spike"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert start.status_code == 201
    run_id = start.json()["run_id"]

    cancel = await client.post(
        f"/api/agitator/runs/{run_id}/cancel",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert cancel.status_code == 200

    # The scenario coroutine MUST observe CancelledError. If it doesn't,
    # this wait_for times out and the test fails — guarding against the
    # task-assignment gap and other silent-cancel bugs.
    await asyncio.wait_for(cancel_observed.wait(), timeout=2.0)

    final = await client.get(
        f"/api/agitator/runs/{run_id}",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    body = final.json()
    assert body["state"] == "cancelled"
    assert body["ended_at"] is not None


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


async def _noop_task() -> None:
    return


async def _start_run_for_test(registry: RunRegistry, run_id: str, scenario: str) -> None:
    """Start a run via try_start with a no-op task. Used by registry unit tests."""
    record = RunRecord(
        run_id=run_id,
        scenario_name=scenario,
        params={},
        started_at=datetime.now(tz=UTC),
    )
    await registry.try_start(
        record,
        max_concurrent=999,
        task_factory=lambda: asyncio.create_task(_noop_task()),
    )


async def test_registry_evicts_oldest_terminal_record_when_full(client) -> None:
    """Eviction rule: when the buffer is at capacity, the oldest non-running
    record is dropped — explicitly, with `_by_id` cleaned up. We never rely
    on `deque.maxlen` for correctness.
    """
    from log_dashboard.agitator.runs import RunRegistry

    registry = RunRegistry(max_recent=3)

    # Start three runs and finalize them so the buffer fills with terminal records.
    for i in range(3):
        await _start_run_for_test(registry, f"r{i}", f"scenario-{i}")
        await registry.finalize(f"r{i}", "succeeded")

    # Adding a 4th must evict the oldest (r0). _by_id must reflect the eviction.
    await _start_run_for_test(registry, "r3", "scenario-3")

    recent = await registry.list_recent()
    assert [r.run_id for r in recent] == ["r1", "r2", "r3"]
    assert await registry.get("r0") is None  # _by_id was cleaned up
    assert (await registry.get("r3")) is not None


async def test_registry_full_with_all_running_raises(client) -> None:
    """Defensive: when the buffer is at capacity AND every record is running,
    try_start raises RegistryFullError rather than silently corrupting state."""
    from log_dashboard.agitator.runs import RegistryFullError, RunRegistry

    registry = RunRegistry(max_recent=2)

    # Fill the buffer with running records (different scenarios so the
    # same-scenario gate doesn't intercept first).
    await _start_run_for_test(registry, "r0", "scenario-a")
    await _start_run_for_test(registry, "r1", "scenario-b")

    # Try to add a 3rd with a high cap so cap doesn't intercept. With every
    # record still `running`, eviction can't find a terminal record.
    record = RunRecord(
        run_id="r2",
        scenario_name="scenario-c",
        params={},
        started_at=datetime.now(tz=UTC),
    )
    with pytest.raises(RegistryFullError):
        await registry.try_start(
            record,
            max_concurrent=999,
            task_factory=lambda: asyncio.create_task(_noop_task()),
        )


async def test_concurrent_run_cap_enforced_under_contention(
    client, valid_token, stub_bootstrap, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TOCTOU fix verification: launch many concurrent POSTs and confirm the
    cap holds.

    Uses a SLOW stub scenario so runs stay `running` long enough for the
    cap check on subsequent requests to actually see N running records.
    The default no-op stub finishes before the next request arrives, which
    would let the cap pass legitimately and mask the bug.
    """
    from log_dashboard.agitator.scenarios import SCENARIOS

    async def _slow_run(self) -> None:
        await asyncio.sleep(1.0)

    for cls in SCENARIOS.values():
        monkeypatch.setattr(cls, "run", _slow_run)

    headers = {"Authorization": f"Bearer {valid_token}"}
    # Default cap is 2. Fire 4 concurrent starts for DIFFERENT scenarios so
    # the same-scenario guard doesn't intercept first.
    scenarios = ["auth-spike", "payload-fuzz", "policy-not-found", "claim-burst"]
    responses = await asyncio.gather(
        *[
            client.post("/api/agitator/runs", json={"scenario": s}, headers=headers)
            for s in scenarios
        ]
    )
    statuses = sorted(r.status_code for r in responses)
    # At most 2 should succeed (cap=2); the rest must be 429.
    assert statuses.count(201) <= 2
    assert statuses.count(429) >= len(scenarios) - 2
