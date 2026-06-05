"""claim-burst — N valid FNOL claim submissions over a bounded window.

The only scenario that writes DB rows. Loads the customer's policy via
CP at run start to recover real policy_number + vin + customer_id, then
posts N valid claims. Each POST produces a 201 + INFO `claim_submitted`
line in FNOL and a 201 + INFO `request` line in SDA.

Postgres gains `count` rows per invocation. Reset via
`docker compose down && docker volume rm agentic-log-analysis-system_postgres-data`.
"""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime, timedelta

from ..http_client import build_client
from .base import Scenario, ScenarioParam, ScenarioSpec, register


@register
class ClaimBurst(Scenario):
    spec = ScenarioSpec(
        name="claim-burst",
        display_name="Claim burst",
        description="200 valid FNOL claim submissions over 60 seconds. "
        "Writes Postgres rows; produces INFO traffic only.",
        target_app="fnol",
        params=(
            ScenarioParam(name="count", minimum=1, maximum=500, default=200),
            ScenarioParam(name="duration_s", minimum=1, maximum=600, default=60),
        ),
    )

    async def run(self) -> None:
        count = self.params.get("count", self.spec.params[0].default)
        duration_s = self.params.get("duration_s", self.spec.params[1].default)
        interval = duration_s / max(count, 1)
        semaphore = asyncio.Semaphore(
            min(self.settings.agitator_default_concurrency, max(count, 1))
        )

        policy = await self._lookup_first_policy()
        if policy is None:
            # No policy → nothing valid to submit. Mark every intended request
            # as failed so the operator sees the scenario produced zero traffic.
            for _ in range(count):
                await self.registry.mark_failure(self.run_id, "no policy found for customer")
            return

        customer_id = policy["customer_id"]
        policy_number = policy["policy_number"]
        vin = (policy.get("vehicles") or [{"vin": "UNKNOWN"}])[0]["vin"]

        headers = {"Authorization": f"Bearer {self.session.fnol_jwt}"}
        rng = random.Random()

        async with build_client(self.settings.fnol_base_url) as client:

            async def send() -> tuple[int, bool]:
                incident_at = (
                    datetime.now(tz=UTC) - timedelta(minutes=rng.randint(1, 60 * 24))
                ).isoformat()
                body = {
                    "customer_id": customer_id,
                    "policy_number": policy_number,
                    "vin": vin,
                    "incident_at": incident_at,
                    "description": "Synthetic claim from Agitator claim-burst scenario.",
                }
                response = await client.post("/fnol/submit", json=body, headers=headers)
                return response.status_code, response.status_code == 201

            tasks: list[asyncio.Task[None]] = []
            for _ in range(count):
                tasks.append(asyncio.create_task(self._fire(send, semaphore)))
                await asyncio.sleep(interval)
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _lookup_first_policy(self) -> dict | None:
        """Fetch the seeded customer's first policy via CP `/policies/me`."""
        headers = {"Authorization": f"Bearer {self.session.cp_jwt}"}
        async with build_client(self.settings.customer_portal_base_url) as client:
            response = await client.get("/policies/me", headers=headers)
            if response.status_code != 200:
                return None
            policies = response.json()
            if not isinstance(policies, list) or not policies:
                return None
            return policies[0]
