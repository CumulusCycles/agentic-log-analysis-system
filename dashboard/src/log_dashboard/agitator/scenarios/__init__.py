"""Scenario registry.

Importing each scenario module registers it via the `@register` decorator
in `base.py`. The router uses `SCENARIOS` to render the UI cards and
dispatch run requests.
"""

from . import (
    ap_degraded,
    ap_read_burst,
    auth_spike,
    claim_burst,
    cp_degraded,
    cp_read_burst,
    error_burst,
    payload_fuzz,
    policy_not_found,
    sda_degraded,
)
from .base import SCENARIOS, Scenario, ScenarioSpec

__all__ = [
    "SCENARIOS",
    "Scenario",
    "ScenarioSpec",
    "ap_degraded",
    "ap_read_burst",
    "auth_spike",
    "claim_burst",
    "cp_degraded",
    "cp_read_burst",
    "error_burst",
    "payload_fuzz",
    "policy_not_found",
    "sda_degraded",
]
