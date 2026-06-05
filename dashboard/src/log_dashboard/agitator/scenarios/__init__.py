"""Scenario registry.

Importing each scenario module registers it via the `@register` decorator
in `base.py`. The router uses `SCENARIOS` to render the UI cards and
dispatch run requests.
"""

from . import auth_spike, claim_burst, payload_fuzz, policy_not_found, sda_degraded
from .base import SCENARIOS, Scenario, ScenarioSpec

__all__ = [
    "SCENARIOS",
    "Scenario",
    "ScenarioSpec",
    "auth_spike",
    "claim_burst",
    "payload_fuzz",
    "policy_not_found",
    "sda_degraded",
]
