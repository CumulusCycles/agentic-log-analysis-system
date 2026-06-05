"""policy-not-found — N lookups for nonexistent policy IDs via FNOL.

FNOL's `GET /fnol/{claim_id}` proxies to SDA; a nonexistent ID returns
404. The request-logger middlewares produce INFO lines in both apps —
INFO lines are filtered out by the default ingest gate, so this scenario
adds activity to the operator-facing /api/logs view (which reads volumes
directly) but does NOT drive WARN/ERROR signal into Chroma.

Trade-off: kept in the starter pack because operators benefit from
seeing 404 traffic in the Log Explorer when validating filters. The
WARN/ERROR-producing scenarios are auth-spike, payload-fuzz, sda-degraded.
"""

from __future__ import annotations

import asyncio
import uuid

from ..http_client import build_client
from .base import Scenario, ScenarioParam, ScenarioSpec, register


@register
class PolicyNotFound(Scenario):
    spec = ScenarioSpec(
        name="policy-not-found",
        display_name="Policy not found",
        description="30 lookups for nonexistent claim IDs via FNOL (404). "
        "INFO traffic only — visible in Log Explorer but not embedded.",
        target_app="fnol",
        params=(
            ScenarioParam(name="count", minimum=1, maximum=200, default=30),
            ScenarioParam(name="duration_s", minimum=1, maximum=300, default=20),
        ),
    )

    async def run(self) -> None:
        count = self.params.get("count", self.spec.params[0].default)
        duration_s = self.params.get("duration_s", self.spec.params[1].default)
        interval = duration_s / max(count, 1)
        semaphore = asyncio.Semaphore(
            min(self.settings.agitator_default_concurrency, max(count, 1))
        )

        headers = {"Authorization": f"Bearer {self.session.fnol_jwt}"}

        async with build_client(self.settings.fnol_base_url) as client:

            async def send() -> tuple[int, bool]:
                bogus_id = str(uuid.uuid4())
                response = await client.get(f"/fnol/{bogus_id}", headers=headers)
                # 404 is the expected outcome.
                return response.status_code, response.status_code == 404

            tasks: list[asyncio.Task[None]] = []
            for _ in range(count):
                tasks.append(asyncio.create_task(self._fire(send, semaphore)))
                await asyncio.sleep(interval)
            await asyncio.gather(*tasks, return_exceptions=True)
