"""ap-read-burst — N GET /api/claims reads against Agent Portal.

Drives INFO traffic at both the Agent Portal (Logback request log) and
the Shared Data API (AP proxies the read through `/claims?...`). No
chaos directives; no DB writes; pure read load.

Useful for populating AP-tagged log lines so the Log Generator UI has a
non-chaos card per portal and the operator can see AP working end-to-end
without flipping `ENABLE_CHAOS`.
"""

from __future__ import annotations

from ..http_client import build_client
from .base import Scenario, ScenarioParam, ScenarioSpec, register


@register
class ApReadBurst(Scenario):
    spec = ScenarioSpec(
        name="ap-read-burst",
        display_name="AP read burst",
        description="100 GETs to Agent Portal /api/claims over 30 seconds. "
        "Produces INFO traffic at AP and SDA; no DB writes.",
        target_app="agent-portal",
        params=(
            ScenarioParam(name="count", minimum=1, maximum=500, default=100),
            ScenarioParam(name="duration_s", minimum=1, maximum=600, default=30),
        ),
    )

    async def run(self) -> None:
        count = self.params.get("count", self.spec.params[0].default)
        duration_s = self.params.get("duration_s", self.spec.params[1].default)

        headers = {"Authorization": f"Bearer {self.session.ap_jwt}"}

        async with build_client(self.settings.agent_portal_base_url) as client:

            async def send() -> tuple[int, bool]:
                response = await client.get("/api/claims", headers=headers)
                return response.status_code, response.status_code == 200

            await self._run_paced(count, duration_s, send)
