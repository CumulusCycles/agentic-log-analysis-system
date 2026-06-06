"""ap-degraded — slow-chaos hammered at Agent Portal for a bounded window.

Hits AP `/api/claims` with `X-Chaos: slow:300`. AP's ChaosFilter (filter
order 20, scoped to `/api/*`) honors the directive and logs `chaos_honored`
at WARN per the PR 4c level split. Requires `ENABLE_CHAOS=true` — the
router rejects with 409 otherwise.

Mirrors `sda-degraded` / `cp-degraded` structurally for cross-app
correlation experiments.
"""

from __future__ import annotations

from ..http_client import build_client
from .base import Scenario, ScenarioParam, ScenarioSpec, register

_CHAOS_DELAY_MS = 300


@register
class ApDegraded(Scenario):
    spec = ScenarioSpec(
        name="ap-degraded",
        display_name="AP degraded",
        description=f"80 GETs to Agent Portal /api/claims with X-Chaos: slow:{_CHAOS_DELAY_MS} "
        "over 60s. Produces chaos_honored WARN lines at AP. Requires ENABLE_CHAOS=true.",
        target_app="agent-portal",
        requires_chaos=True,
        params=(
            ScenarioParam(name="count", minimum=1, maximum=500, default=80),
            ScenarioParam(name="duration_s", minimum=1, maximum=600, default=60),
        ),
    )

    async def run(self) -> None:
        count = self.params.get("count", self.spec.params[0].default)
        duration_s = self.params.get("duration_s", self.spec.params[1].default)

        headers = {
            "Authorization": f"Bearer {self.session.ap_jwt}",
            "X-Chaos": f"slow:{_CHAOS_DELAY_MS}",
        }

        async with build_client(self.settings.agent_portal_base_url, timeout=15.0) as client:

            async def send() -> tuple[int, bool]:
                response = await client.get("/api/claims", headers=headers)
                return response.status_code, response.status_code == 200

            await self._run_paced(count, duration_s, send)
