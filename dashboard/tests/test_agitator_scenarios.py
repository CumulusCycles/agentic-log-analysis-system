"""Tests for the 5 scenarios — header enforcement, counters, cancellation.

Each scenario is exercised against an `httpx.MockTransport` rather than a
live target app. Tests assert the three properties that matter:
1. `X-Source: synthetic` is set on every request
2. `X-Chaos` is only set by `sda-degraded`
3. The registry's sent/succeeded/failed counters reflect the run
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from log_dashboard.agitator.auth import AppSession
from log_dashboard.agitator.runs import RunRecord, RunRegistry
from log_dashboard.agitator.scenarios.auth_spike import AuthSpike
from log_dashboard.agitator.scenarios.claim_burst import ClaimBurst
from log_dashboard.agitator.scenarios.payload_fuzz import PayloadFuzz
from log_dashboard.agitator.scenarios.policy_not_found import PolicyNotFound
from log_dashboard.agitator.scenarios.sda_degraded import SdaDegraded
from log_dashboard.config import get_settings


def _fake_session() -> AppSession:
    return AppSession(
        fnol_jwt="fake-fnol",
        cp_jwt="fake-cp",
        ap_jwt="fake-ap",
        sda_customer_jwt="fake-cp",
        sda_api_key_cp="fake-api-key",
    )


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def registry():
    return RunRegistry()


async def _noop_task() -> None:
    return


async def _add_running(registry: RunRegistry, run_id: str = "test-run") -> None:
    """Insert a running record so scenario.run()'s counter updates can land.

    Scenario tests drive `scenario.run()` directly rather than via the
    router, so the task created by try_start is unused — a no-op task is
    sufficient to satisfy the try_start contract.
    """
    record = RunRecord(
        run_id=run_id,
        scenario_name="test",
        params={},
        started_at=datetime.now(tz=UTC),
    )
    await registry.try_start(
        record,
        max_concurrent=999,
        task_factory=lambda: asyncio.create_task(_noop_task()),
    )


def _mock_transport(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _patch_build_client(monkeypatch, captured: list[httpx.Request]):
    """Replace `build_client` everywhere it's imported with a MockTransport
    variant that records every request into `captured`."""

    from log_dashboard.agitator import http_client as hc
    from log_dashboard.agitator.scenarios import (
        auth_spike,
        claim_burst,
        payload_fuzz,
        policy_not_found,
        sda_degraded,
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        # Routes the tests care about each return a body shape; default 200.
        if request.url.path == "/policies/me":
            return httpx.Response(
                200,
                json=[
                    {
                        "policy_number": "POL-1",
                        "customer_id": "cust-1",
                        "vehicles": [{"vin": "VIN-1"}],
                    }
                ],
            )
        if request.url.path.endswith("/auth/login"):
            return httpx.Response(401, json={"detail": "invalid credentials"})
        if request.url.path == "/fnol/submit":
            # claim-burst sends valid bodies, payload-fuzz invalid. Return 201
            # for bodies that look complete; 422 otherwise.
            try:
                body = request.content
                # crude shape check
                if b"VIN-1" in body and b"POL-1" in body:
                    return httpx.Response(201, json={"id": "claim-1"})
            except Exception:
                pass
            return httpx.Response(422, json={"detail": "invalid"})
        if request.url.path.startswith("/fnol/"):
            return httpx.Response(404, json={"detail": "not found"})
        if request.url.path == "/policies":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={})

    def _build_mock(base_url, *, timeout=10.0, extra_headers=None, transport=None):
        return (
            hc.build_client.__wrapped__(  # type: ignore[attr-defined]
                base_url=base_url,
                timeout=timeout,
                extra_headers=extra_headers,
                transport=_mock_transport(_handler),
            )
            if hasattr(hc.build_client, "__wrapped__")
            else httpx.AsyncClient(
                base_url=base_url,
                timeout=timeout,
                headers={
                    "X-Source": "synthetic",
                    **(extra_headers or {}),
                },
                transport=_mock_transport(_handler),
            )
        )

    # Patch every importer.
    for module in (hc, auth_spike, payload_fuzz, policy_not_found, claim_burst, sda_degraded):
        monkeypatch.setattr(module, "build_client", _build_mock)


async def test_auth_spike_sends_x_source_synthetic_on_every_request(
    monkeypatch: pytest.MonkeyPatch, settings, registry
) -> None:
    captured: list[httpx.Request] = []
    _patch_build_client(monkeypatch, captured)
    await _add_running(registry, "as1")

    scenario = AuthSpike(
        settings=settings,
        session=_fake_session(),
        registry=registry,
        run_id="as1",
        params={"count": 5, "duration_s": 1},
    )
    await scenario.run()

    assert len(captured) == 5
    for req in captured:
        assert req.headers.get("X-Source") == "synthetic"
        assert "X-Chaos" not in req.headers

    record = await registry.get("as1")
    assert record is not None
    assert record.sent == 5
    # All 401s = expected outcome = counted as `succeeded`.
    assert record.succeeded == 5
    assert record.failed == 0


async def test_payload_fuzz_treats_4xx_as_succeeded(
    monkeypatch: pytest.MonkeyPatch, settings, registry
) -> None:
    captured: list[httpx.Request] = []
    _patch_build_client(monkeypatch, captured)
    await _add_running(registry, "pf1")

    scenario = PayloadFuzz(
        settings=settings,
        session=_fake_session(),
        registry=registry,
        run_id="pf1",
        params={"count": 5, "duration_s": 1},
    )
    await scenario.run()

    record = await registry.get("pf1")
    assert record is not None
    assert record.sent == 5
    # All mocked bodies fail the shape check → 422 → succeeded.
    assert record.succeeded == 5


async def test_policy_not_found_treats_404_as_succeeded(
    monkeypatch: pytest.MonkeyPatch, settings, registry
) -> None:
    captured: list[httpx.Request] = []
    _patch_build_client(monkeypatch, captured)
    await _add_running(registry, "pn1")

    scenario = PolicyNotFound(
        settings=settings,
        session=_fake_session(),
        registry=registry,
        run_id="pn1",
        params={"count": 3, "duration_s": 1},
    )
    await scenario.run()

    record = await registry.get("pn1")
    assert record is not None
    assert record.sent == 3
    assert record.succeeded == 3


async def test_claim_burst_posts_valid_bodies(
    monkeypatch: pytest.MonkeyPatch, settings, registry
) -> None:
    captured: list[httpx.Request] = []
    _patch_build_client(monkeypatch, captured)
    await _add_running(registry, "cb1")

    scenario = ClaimBurst(
        settings=settings,
        session=_fake_session(),
        registry=registry,
        run_id="cb1",
        params={"count": 3, "duration_s": 1},
    )
    await scenario.run()

    record = await registry.get("cb1")
    assert record is not None
    # One /policies/me lookup + 3 /fnol/submit posts = 4 captured.
    submit_requests = [r for r in captured if r.url.path == "/fnol/submit"]
    assert len(submit_requests) == 3
    for req in submit_requests:
        assert req.headers.get("X-Source") == "synthetic"
        assert req.headers.get("Authorization") == "Bearer fake-fnol"
    assert record.succeeded == 3


async def test_sda_degraded_sets_x_chaos_header(
    monkeypatch: pytest.MonkeyPatch, settings, registry
) -> None:
    captured: list[httpx.Request] = []
    _patch_build_client(monkeypatch, captured)
    await _add_running(registry, "sd1")

    scenario = SdaDegraded(
        settings=settings,
        session=_fake_session(),
        registry=registry,
        run_id="sd1",
        params={"count": 3, "duration_s": 1},
    )
    await scenario.run()

    assert len(captured) == 3
    for req in captured:
        assert req.headers.get("X-Source") == "synthetic"
        assert req.headers.get("X-Chaos") == "slow:500"
        assert req.headers.get("X-API-Key") == "fake-api-key"


async def test_auth_spike_cancellation_stops_remaining_fires(
    monkeypatch: pytest.MonkeyPatch, settings, registry
) -> None:
    """Start a scenario, cancel before all fires complete, assert sent < count."""
    captured: list[httpx.Request] = []
    _patch_build_client(monkeypatch, captured)
    await _add_running(registry, "cancel1")

    scenario = AuthSpike(
        settings=settings,
        session=_fake_session(),
        registry=registry,
        run_id="cancel1",
        params={"count": 100, "duration_s": 10},
    )

    task = asyncio.create_task(scenario.run())
    # Let a few fires land, then cancel.
    await asyncio.sleep(0.3)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    record = await registry.get("cancel1")
    assert record is not None
    assert record.sent < 100


async def test_claim_burst_no_policy_marks_all_failed(
    monkeypatch: pytest.MonkeyPatch, settings, registry
) -> None:
    """If /policies/me returns empty, claim-burst fails every intended fire."""
    captured: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == "/policies/me":
            return httpx.Response(200, json=[])  # no policy
        return httpx.Response(200, json={})

    from log_dashboard.agitator import http_client as hc
    from log_dashboard.agitator.scenarios import claim_burst as cb_module

    def _build_mock(base_url, *, timeout=10.0, extra_headers=None, transport=None):
        return httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"X-Source": "synthetic", **(extra_headers or {})},
            transport=httpx.MockTransport(_handler),
        )

    for module in (hc, cb_module):
        monkeypatch.setattr(module, "build_client", _build_mock)

    await _add_running(registry, "cbnp")
    scenario = ClaimBurst(
        settings=settings,
        session=_fake_session(),
        registry=registry,
        run_id="cbnp",
        params={"count": 4, "duration_s": 1},
    )
    await scenario.run()

    record = await registry.get("cbnp")
    assert record is not None
    assert record.failed == 4
    assert record.sent == 0  # no /fnol/submit calls actually issued
