"""auth-spike — N failed FNOL logins over a bounded window.

Drives `login_failed` WARN lines through FNOL (which proxies to SDA), so
both apps emit one WARN per request. Bad-password is the failure mode —
the username (`alice`) is a real seeded customer, so SDA's failed-login
log has `reason=bad_password` rather than `user_not_found`.
"""

from __future__ import annotations

from ..http_client import build_client
from .base import Scenario, ScenarioParam, ScenarioSpec, register


@register
class AuthSpike(Scenario):
    spec = ScenarioSpec(
        name="auth-spike",
        display_name="Auth spike",
        description="50 failed FNOL logins over 30 seconds (wrong password). "
        "Produces login_failed WARN lines in FNOL + SDA.",
        target_app="fnol",
        params=(
            ScenarioParam(name="count", minimum=1, maximum=500, default=50),
            ScenarioParam(name="duration_s", minimum=1, maximum=300, default=30),
        ),
    )

    async def run(self) -> None:
        count = self.params.get("count", self.spec.params[0].default)
        duration_s = self.params.get("duration_s", self.spec.params[1].default)
        username = self.settings.agitator_customer_username

        async with build_client(self.settings.fnol_base_url) as client:

            async def send() -> tuple[int, bool]:
                response = await client.post(
                    "/auth/login",
                    json={"username": username, "password": "wrong-password-on-purpose"},
                )
                # 401 is the expected outcome.
                return response.status_code, response.status_code == 401

            await self._run_paced(count, duration_s, send)
