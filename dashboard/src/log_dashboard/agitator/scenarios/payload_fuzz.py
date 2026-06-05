"""payload-fuzz — N invalid FNOL claim submissions over a bounded window.

Each request POSTs an intentionally malformed body to `/fnol/submit`.
FastAPI's pydantic validation rejects with 422 (or SDA rejects with 400
on the lookup paths). Produces `claim_validation_rejected` / WARN lines
in SDA and `fnol_validation_failed` lines in FNOL.
"""

from __future__ import annotations

import random

from ..http_client import build_client
from .base import Scenario, ScenarioParam, ScenarioSpec, register

_BAD_BODIES: list[dict[str, object]] = [
    {},  # empty body
    {"policy_number": "POL-XXX"},  # missing required fields
    {"policy_number": "POL-DOES-NOT-EXIST", "incident_at": "not-a-date"},
    {"policy_number": 12345, "incident_at": "2026-06-04T12:00:00Z"},  # wrong type
    {"policy_number": "POL-1", "incident_at": "2026-06-04T12:00:00Z", "vin": ""},
]


@register
class PayloadFuzz(Scenario):
    spec = ScenarioSpec(
        name="payload-fuzz",
        display_name="Payload fuzz",
        description="100 invalid FNOL claim submissions over 60 seconds. "
        "Produces validation WARN lines in FNOL + SDA.",
        target_app="fnol",
        params=(
            ScenarioParam(name="count", minimum=1, maximum=1000, default=100),
            ScenarioParam(name="duration_s", minimum=1, maximum=600, default=60),
        ),
    )

    async def run(self) -> None:
        count = self.params.get("count", self.spec.params[0].default)
        duration_s = self.params.get("duration_s", self.spec.params[1].default)

        rng = random.Random()
        headers = {"Authorization": f"Bearer {self.session.fnol_jwt}"}

        async with build_client(self.settings.fnol_base_url) as client:

            async def send() -> tuple[int, bool]:
                body = rng.choice(_BAD_BODIES)
                response = await client.post("/fnol/submit", json=body, headers=headers)
                # 4xx is the expected rejection. 5xx counts as `failed`.
                ok = 400 <= response.status_code < 500
                return response.status_code, ok

            await self._run_paced(count, duration_s, send)
