"""Verify the simulator's state machine and the DB enum are kept in sync."""

import pytest

from shared_data_api.db.models import CLAIM_STATUS_VALUES
from shared_data_api.simulator.claim_status import (
    TERMINAL,
    TRANSITIONS,
    _validate_status_coverage,
)


def test_every_declared_status_is_either_a_source_or_terminal():
    declared = set(CLAIM_STATUS_VALUES)
    covered = set(TRANSITIONS.keys()) | TERMINAL
    assert declared == covered


def test_no_transition_targets_unknown_status():
    declared = set(CLAIM_STATUS_VALUES)
    for source, choices in TRANSITIONS.items():
        for target, _weight in choices:
            assert target in declared, f"{source} -> {target}"


def test_validate_status_coverage_runs_clean():
    """The function should not raise under current configuration."""
    _validate_status_coverage()


def test_validate_status_coverage_detects_missing(monkeypatch):
    """A new enum value with no transition/terminal handling must raise."""
    import shared_data_api.simulator.claim_status as sim

    monkeypatch.setattr(sim, "CLAIM_STATUS_VALUES", (*sim.CLAIM_STATUS_VALUES, "blocked"))
    with pytest.raises(RuntimeError, match="missing handling"):
        sim._validate_status_coverage()


def test_validate_status_coverage_detects_extra(monkeypatch):
    """A TRANSITIONS key that isn't in the enum must raise."""
    import shared_data_api.simulator.claim_status as sim

    monkeypatch.setitem(sim.TRANSITIONS, "bogus_status", [("triaged", 0.5)])
    with pytest.raises(RuntimeError, match="not in CLAIM_STATUS_VALUES"):
        sim._validate_status_coverage()


def test_validate_status_coverage_detects_unknown_target(monkeypatch):
    """A transition pointing to a status not in the enum must raise."""
    import shared_data_api.simulator.claim_status as sim

    monkeypatch.setitem(sim.TRANSITIONS, "submitted", [("nonexistent_status", 1.0)])
    with pytest.raises(RuntimeError, match="unknown status"):
        sim._validate_status_coverage()
