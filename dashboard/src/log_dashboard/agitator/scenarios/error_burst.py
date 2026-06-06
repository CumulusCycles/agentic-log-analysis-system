"""error-burst — chaos-driven 5xx burst hammered at SDA.

Hits SDA directly with `X-Chaos: error:500` so each request short-circuits
to a 500 response AND logs `chaos_honored` at ERROR level (per the PR 4c
chaos middleware level split — 5xx is ERROR, 4xx stays WARN). Drives the
ERROR-tier signal the proactive scan needs to detect anomalies.

Mirrors `sda_degraded` structurally; the only differences are the chaos
directive (`error:500` instead of `slow:500`), the expected status code
(500 instead of 200), and the description copy. Requires
`ENABLE_CHAOS=true` — the router rejects with 409 otherwise.

SDA-direct call uses CP's API key + the customer JWT (per ADR-005, the
JWT is signed by SDA itself, so it works against SDA's auth layer
regardless of which app issued it via login proxy). Every outbound
request also carries `X-Source: synthetic` automatically — set at the
single seam in `agitator.http_client.build_client`.
"""

from __future__ import annotations

from ..http_client import build_client
from .base import Scenario, ScenarioParam, ScenarioSpec, register

_CHAOS_ERROR_STATUS = 500


@register
class ErrorBurst(Scenario):
    spec = ScenarioSpec(
        name="error-burst",
        display_name="Error burst",
        description=(
            f"120 SDA reads with X-Chaos: error:{_CHAOS_ERROR_STATUS} over 60s. "
            "Produces chaos_honored ERROR lines so the proactive scan has "
            "ERROR-tier signal in Chroma. Requires ENABLE_CHAOS=true."
        ),
        target_app="shared-data-api",
        requires_chaos=True,
        params=(
            ScenarioParam(name="count", minimum=1, maximum=1000, default=120),
            ScenarioParam(name="duration_s", minimum=1, maximum=600, default=60),
        ),
    )

    async def run(self) -> None:
        count = self.params.get("count", self.spec.params[0].default)
        duration_s = self.params.get("duration_s", self.spec.params[1].default)

        headers = {
            "X-API-Key": self.session.sda_api_key_cp,
            "Authorization": f"Bearer {self.session.sda_customer_jwt}",
            "X-Chaos": f"error:{_CHAOS_ERROR_STATUS}",
        }

        async with build_client(self.settings.shared_data_api_base_url, timeout=15.0) as client:

            async def send() -> tuple[int, bool]:
                # /policies is the same target as sda_degraded so caller +
                # path correlation matches across the two chaos scenarios.
                # Expected outcome is 500 (chaos short-circuits before the
                # handler runs); we count those as the success case for
                # this scenario.
                response = await client.get("/policies", headers=headers)
                return response.status_code, response.status_code == _CHAOS_ERROR_STATUS

            await self._run_paced(count, duration_s, send)
