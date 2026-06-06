"""cp-degraded — slow-chaos hammered at Customer Portal for a bounded window.

Hits CP `/policies/me` with `X-Chaos: slow:300` so the request-handling
chain delays before returning. CP's chaos middleware logs `chaos_honored`
at WARN per the PR 4c level split (slow → WARN regardless of duration).
Requires `ENABLE_CHAOS=true` — the router rejects with 409 otherwise.

Mirrors `sda-degraded` structurally so the operator has one degraded
scenario per portal (and SDA) for cross-app correlation experiments.
"""

from __future__ import annotations

from ..http_client import build_client
from .base import Scenario, ScenarioParam, ScenarioSpec, register

_CHAOS_DELAY_MS = 300


@register
class CpDegraded(Scenario):
    spec = ScenarioSpec(
        name="cp-degraded",
        display_name="CP degraded",
        description=f"80 GETs to Customer Portal /policies/me with X-Chaos: slow:{_CHAOS_DELAY_MS} "
        "over 60s. Produces chaos_honored WARN lines at CP. Requires ENABLE_CHAOS=true.",
        target_app="customer-portal",
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
            "Authorization": f"Bearer {self.session.cp_jwt}",
            "X-Chaos": f"slow:{_CHAOS_DELAY_MS}",
        }

        async with build_client(self.settings.customer_portal_base_url, timeout=15.0) as client:

            async def send() -> tuple[int, bool]:
                response = await client.get("/policies/me", headers=headers)
                return response.status_code, response.status_code == 200

            await self._run_paced(count, duration_s, send)
