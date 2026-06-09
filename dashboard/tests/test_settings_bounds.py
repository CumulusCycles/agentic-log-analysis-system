"""Regression guard for the `ge=`/`le=` bounds on Settings fields.

Pydantic enforces these bounds, but a future widening would not be caught
by any other test in the suite — every other test instantiates Settings
inside the bounds. This file is the floor that fails closed if the bounds
shrink, widen, or are removed.

Each parameterised case sets the env var to a value one below `ge` or one
above `le`, instantiates Settings, and asserts a `ValidationError` is
raised. A separate case asserts the boundary value itself (exactly `ge`,
exactly `le`) is accepted — so the test doesn't drift if the bound is
later moved by one unit.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from log_dashboard.config import Settings

# (alias_env_var, ge, le, settings_field_name)
_BOUNDED_FIELDS = [
    ("DASHBOARD_LLM_MAX_TOOL_CALLS_PER_REQUEST", 1, 20, "llm_max_tool_calls_per_request"),
    (
        "DASHBOARD_LLM_MAX_INPUT_TOKENS_PER_REQUEST",
        512,
        64_000,
        "llm_max_input_tokens_per_request",
    ),
    ("DASHBOARD_LLM_MAX_MESSAGES_PER_SESSION", 2, 200, "llm_max_messages_per_session"),
    ("DASHBOARD_LLM_TIMEOUT_SECONDS", 5, 600, "llm_timeout_seconds"),
    ("DASHBOARD_SESSION_INDEX_MAX", 10, 10_000, "session_index_max"),
    (
        "DASHBOARD_PROACTIVE_SCAN_INTERVAL_SECONDS",
        60,
        86_400,
        "proactive_scan_interval_seconds",
    ),
    (
        "DASHBOARD_PROACTIVE_SCAN_LOOKBACK_MINUTES",
        5,
        1440,
        "proactive_scan_lookback_minutes",
    ),
    ("DASHBOARD_PROACTIVE_SCAN_MAX_FINDINGS", 1, 20, "proactive_scan_max_findings"),
    ("AGITATOR_MAX_CONCURRENT_RUNS", 1, 10, "agitator_max_concurrent_runs"),
    ("AGITATOR_DEFAULT_CONCURRENCY", 1, 100, "agitator_default_concurrency"),
]


@pytest.mark.parametrize("env_var,ge,le,_field", _BOUNDED_FIELDS)
def test_settings_rejects_value_below_ge(
    monkeypatch: pytest.MonkeyPatch, env_var: str, ge: int, le: int, _field: str
) -> None:
    """One unit below `ge` must raise `ValidationError`."""
    monkeypatch.setenv(env_var, str(ge - 1))
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


@pytest.mark.parametrize("env_var,ge,le,_field", _BOUNDED_FIELDS)
def test_settings_rejects_value_above_le(
    monkeypatch: pytest.MonkeyPatch, env_var: str, ge: int, le: int, _field: str
) -> None:
    """One unit above `le` must raise `ValidationError`."""
    monkeypatch.setenv(env_var, str(le + 1))
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


@pytest.mark.parametrize("env_var,ge,le,field", _BOUNDED_FIELDS)
def test_settings_accepts_boundary_values(
    monkeypatch: pytest.MonkeyPatch, env_var: str, ge: int, le: int, field: str
) -> None:
    """Exactly `ge` and exactly `le` must be accepted — the bound is inclusive.

    Two assertions per field (lower then upper) keep the test count down
    while still proving inclusivity at both ends.
    """
    monkeypatch.setenv(env_var, str(ge))
    settings = Settings()  # type: ignore[call-arg]
    assert getattr(settings, field) == ge

    monkeypatch.setenv(env_var, str(le))
    settings = Settings()  # type: ignore[call-arg]
    assert getattr(settings, field) == le


def test_settings_rejects_negative_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative values must be rejected — a regression that flipped a
    `ge=5` to `gt=-1` would make this case pass silently."""
    monkeypatch.setenv("DASHBOARD_LLM_TIMEOUT_SECONDS", "-1")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_settings_rejects_zero_max_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    """`proactive_scan_max_findings=0` would silently disable the scan
    surface — `ge=1` is load-bearing."""
    monkeypatch.setenv("DASHBOARD_PROACTIVE_SCAN_MAX_FINDINGS", "0")
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
