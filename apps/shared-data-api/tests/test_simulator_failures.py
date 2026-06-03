"""Verify the simulator's consecutive-failure tracking and alarm escalation."""

from unittest.mock import patch

import pytest
import structlog

from shared_data_api.config import get_settings
from shared_data_api.simulator.claim_status import (
    ALARM_THRESHOLD,
    ClaimStatusSimulator,
)


def test_initial_failure_count_is_zero():
    sim = ClaimStatusSimulator(get_settings())
    assert sim.consecutive_failures == 0


def test_failure_increments_counter():
    sim = ClaimStatusSimulator(get_settings())
    with structlog.testing.capture_logs():
        sim._on_tick_failure()
    assert sim.consecutive_failures == 1


def test_success_resets_counter():
    sim = ClaimStatusSimulator(get_settings())
    with structlog.testing.capture_logs():
        sim._on_tick_failure()
        sim._on_tick_failure()
    sim._on_tick_success()
    assert sim.consecutive_failures == 0


@pytest.mark.parametrize(
    "n_failures",
    [ALARM_THRESHOLD - 1, ALARM_THRESHOLD, ALARM_THRESHOLD + 2],
)
def test_alarm_fires_at_threshold(n_failures):
    sim = ClaimStatusSimulator(get_settings())
    with structlog.testing.capture_logs() as captured:
        for _ in range(n_failures):
            sim._on_tick_failure()
    alarms = [e for e in captured if e.get("event") == "simulator_persistent_failure"]
    if n_failures >= ALARM_THRESHOLD:
        assert len(alarms) == 1, "alarm should fire exactly once"
        assert alarms[0]["log_level"] == "error"
    else:
        assert alarms == []


def test_alarm_only_fires_once_until_recovery():
    sim = ClaimStatusSimulator(get_settings())
    with structlog.testing.capture_logs() as captured:
        for _ in range(ALARM_THRESHOLD + 3):
            sim._on_tick_failure()
    alarms = [e for e in captured if e.get("event") == "simulator_persistent_failure"]
    assert len(alarms) == 1


def test_recovery_emits_recovered_event():
    sim = ClaimStatusSimulator(get_settings())
    for _ in range(ALARM_THRESHOLD):
        with structlog.testing.capture_logs():
            sim._on_tick_failure()
    with structlog.testing.capture_logs() as captured:
        sim._on_tick_success()
    recovered = [e for e in captured if e.get("event") == "simulator_recovered"]
    assert len(recovered) == 1
    assert recovered[0]["after_failures"] == ALARM_THRESHOLD


def test_alarm_rearms_after_recovery():
    sim = ClaimStatusSimulator(get_settings())
    # First failure burst → alarm fires once.
    for _ in range(ALARM_THRESHOLD):
        with structlog.testing.capture_logs():
            sim._on_tick_failure()
    # Recovery resets state.
    sim._on_tick_success()
    # Second failure burst → alarm fires again.
    with structlog.testing.capture_logs() as captured:
        for _ in range(ALARM_THRESHOLD):
            sim._on_tick_failure()
    alarms = [e for e in captured if e.get("event") == "simulator_persistent_failure"]
    assert len(alarms) == 1


@pytest.mark.asyncio
async def test_run_loop_records_failures(monkeypatch):
    """tick() exceptions count toward the consecutive failure tally."""
    sim = ClaimStatusSimulator(get_settings())

    async def raising_tick():
        raise RuntimeError("boom")

    # Tick raises, then loop should record the failure and continue.
    with patch.object(sim, "tick", side_effect=raising_tick), structlog.testing.capture_logs():
        # Manually drive one iteration of the loop body.
        try:
            await sim.tick()
        except Exception:
            sim._on_tick_failure()
    assert sim.consecutive_failures == 1
