"""cp-read-burst — N GET /policies/me reads against Customer Portal.

Drives INFO traffic at both the Customer Portal (request log) and the
Shared Data API (CP proxies the read through `/policies?customer_id=...`).
No chaos directives; no DB writes; pure read load.

Useful for populating CP-tagged log lines so the Log Generator UI has a
non-chaos card per portal and the operator can see CP working end-to-end
without flipping `ENABLE_CHAOS`.
"""

from __future__ import annotations

from ..http_client import build_client
from .base import Scenario, ScenarioParam, ScenarioSpec, register


@register
class CpReadBurst(Scenario):
    spec = ScenarioSpec(
        name="cp-read-burst",
        display_name="CP read burst",
        description="100 GETs to Customer Portal /policies/me over 30 seconds. "
        "Produces INFO traffic at CP and SDA; no DB writes.",
        target_app="customer-portal",
        params=(
            ScenarioParam(name="count", minimum=1, maximum=500, default=100),
            ScenarioParam(name="duration_s", minimum=1, maximum=600, default=30),
        ),
    )

    async def run(self) -> None:
        count = self.params.get("count", self.spec.params[0].default)
        duration_s = self.params.get("duration_s", self.spec.params[1].default)

        headers = {"Authorization": f"Bearer {self.session.cp_jwt}"}

        async with build_client(self.settings.customer_portal_base_url) as client:

            async def send() -> tuple[int, bool]:
                response = await client.get("/policies/me", headers=headers)
                return response.status_code, response.status_code == 200

            await self._run_paced(count, duration_s, send)
