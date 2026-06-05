"""sda-degraded — slow-chaos hammered at SDA for a bounded window.

Hits SDA directly with `X-Chaos: slow:500` so each request emits a
`chaos_honored` WARN line. Drives the WARN volume the LangGraph agent
(PR 4) needs to recognize as an induced cascade. Requires
`ENABLE_CHAOS=true` — the router rejects with 409 otherwise.

SDA-direct call uses CP's API key + the customer JWT (per ADR-005,
the JWT is signed by SDA itself, so it works against SDA's auth
layer regardless of which app issued it via login proxy).
"""

from __future__ import annotations

import asyncio

from ..http_client import build_client
from .base import Scenario, ScenarioParam, ScenarioSpec, register

_CHAOS_DELAY_MS = 500


@register
class SdaDegraded(Scenario):
    spec = ScenarioSpec(
        name="sda-degraded",
        display_name="SDA degraded",
        description=f"240 SDA reads with X-Chaos: slow:{_CHAOS_DELAY_MS} over 120s. "
        "Produces chaos_honored WARN lines. Requires ENABLE_CHAOS=true.",
        target_app="shared-data-api",
        requires_chaos=True,
        params=(
            ScenarioParam(name="count", minimum=1, maximum=1000, default=240),
            ScenarioParam(name="duration_s", minimum=1, maximum=600, default=120),
        ),
    )

    async def run(self) -> None:
        count = self.params.get("count", self.spec.params[0].default)
        duration_s = self.params.get("duration_s", self.spec.params[1].default)
        interval = duration_s / max(count, 1)
        semaphore = asyncio.Semaphore(
            min(self.settings.agitator_default_concurrency, max(count, 1))
        )

        headers = {
            "X-API-Key": self.session.sda_api_key_cp,
            "Authorization": f"Bearer {self.session.sda_customer_jwt}",
            "X-Chaos": f"slow:{_CHAOS_DELAY_MS}",
        }

        async with build_client(self.settings.shared_data_api_base_url, timeout=15.0) as client:

            async def send() -> tuple[int, bool]:
                # /policies is read-only, returns a list. Slow chaos sleeps
                # _CHAOS_DELAY_MS then forwards; expected outcome is 200.
                response = await client.get("/policies", headers=headers)
                return response.status_code, response.status_code == 200

            tasks: list[asyncio.Task[None]] = []
            for _ in range(count):
                tasks.append(asyncio.create_task(self._fire(send, semaphore)))
                await asyncio.sleep(interval)
            await asyncio.gather(*tasks, return_exceptions=True)
