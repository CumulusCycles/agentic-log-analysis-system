"""Per-run authentication session for the four target apps.

At scenario start the Agitator logs in to FNOL/CP/AP with seeded demo creds
and caches the JWTs. SDA is reached two ways depending on the scenario:
- via FNOL/CP/AP routes (those apps attach their own SDA API key)
- directly with `SHARED_DATA_API_KEY_CUSTOMER_PORTAL` + a customer JWT
  (only `sda-degraded` uses this path)

Credential discipline: this module never logs any password, token, or
bearer value. Only login outcomes (`status`, `app`) are logged. See
`feedback_never_log_credentials`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from ..config import Settings
from ..logging_setup import get_logger
from .http_client import build_client

log = get_logger("agitator.auth")


class AgitatorAuthError(RuntimeError):
    """Raised when one of the per-app logins fails at scenario start."""


@dataclass
class AppSession:
    """JWTs and API keys collected once per scenario run.

    Tokens are never logged. The dataclass is internal to the Agitator
    module and never serialised onto the run-status response.
    """

    fnol_jwt: str
    cp_jwt: str
    ap_jwt: str
    sda_customer_jwt: str
    sda_api_key_cp: str


async def _login(client: httpx.AsyncClient, username: str, password: str, app: str) -> str:
    """POST /auth/login to one of FNOL/CP/AP, return the access_token.

    Never logs the password. Logs only the outcome status.
    """
    try:
        response = await client.post(
            "/auth/login",
            json={"username": username, "password": password},
        )
    except httpx.HTTPError as exc:
        log.warning(
            "agitator_login_failed",
            app=app,
            reason="transport_error",
            error_class=type(exc).__name__,
        )
        raise AgitatorAuthError(f"login to {app} failed: transport error") from exc

    if response.status_code != 200:
        log.warning(
            "agitator_login_failed",
            app=app,
            reason="non_200",
            status=response.status_code,
        )
        raise AgitatorAuthError(f"login to {app} failed: status {response.status_code}")

    body = response.json()
    token = body.get("access_token")
    if not isinstance(token, str) or not token:
        log.warning("agitator_login_failed", app=app, reason="missing_token")
        raise AgitatorAuthError(f"login to {app} returned no access_token")

    log.info("agitator_login_ok", app=app, username=username)
    return token


async def bootstrap_session(settings: Settings) -> AppSession:
    """Log in to FNOL/CP/AP in parallel and gather SDA-direct credentials.

    Tokens land in an `AppSession`. Failures from any app surface as
    `AgitatorAuthError`; the router converts that into a 502 so the
    operator sees the upstream went sideways.
    """
    customer_username = settings.agitator_customer_username
    customer_password = settings.agitator_customer_password
    agent_username = settings.agitator_agent_username
    agent_password = settings.agitator_agent_password

    async with (
        build_client(settings.fnol_base_url) as fnol_client,
        build_client(settings.customer_portal_base_url) as cp_client,
        build_client(settings.agent_portal_base_url) as ap_client,
    ):
        # AP routes the /auth/login through /api/auth/login (controllers under /api/*).
        # Build a thin sub-client by overriding the URL on the call.
        fnol_login, cp_login = await asyncio.gather(
            _login(fnol_client, customer_username, customer_password, app="fnol"),
            _login(cp_client, customer_username, customer_password, app="customer-portal"),
        )
        # AP login lives under /api/auth/login.
        ap_response = await ap_client.post(
            "/api/auth/login",
            json={"username": agent_username, "password": agent_password},
        )
        if ap_response.status_code != 200:
            log.warning(
                "agitator_login_failed",
                app="agent-portal",
                reason="non_200",
                status=ap_response.status_code,
            )
            raise AgitatorAuthError(
                f"login to agent-portal failed: status {ap_response.status_code}"
            )
        ap_token = ap_response.json().get("access_token")
        if not isinstance(ap_token, str) or not ap_token:
            raise AgitatorAuthError("login to agent-portal returned no access_token")
        log.info("agitator_login_ok", app="agent-portal", username=agent_username)
        ap_login = ap_token

    # The CP-issued JWT (cp_login) is signed by SDA — it works as a customer
    # JWT against SDA directly when combined with the CP API key. See ADR-005.
    return AppSession(
        fnol_jwt=fnol_login,
        cp_jwt=cp_login,
        ap_jwt=ap_login,
        sda_customer_jwt=cp_login,
        sda_api_key_cp=settings.shared_data_api_key_customer_portal,
    )
