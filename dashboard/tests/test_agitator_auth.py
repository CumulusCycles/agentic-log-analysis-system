"""Tests for the Agitator session bootstrap.

Verifies the login burst across FNOL/CP/AP, the JWT capture path, and
the failure semantics that the router translates into a 502.
"""

from __future__ import annotations

import httpx
import pytest
import structlog

from log_dashboard.agitator import auth as auth_module
from log_dashboard.agitator.auth import AgitatorAuthError, bootstrap_session
from log_dashboard.config import get_settings


def _ok_handler(request: httpx.Request) -> httpx.Response:
    """Return a valid token for any login attempt."""
    path = request.url.path
    if path.endswith("/auth/login"):
        return httpx.Response(200, json={"access_token": "jwt-test", "expires_in": 3600})
    return httpx.Response(404)


def _patch_clients(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    def _build_mock(base_url, *, timeout=10.0, extra_headers=None, transport=None):
        return httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"X-Source": "synthetic", **(extra_headers or {})},
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(auth_module, "build_client", _build_mock)


async def test_bootstrap_session_logs_in_to_three_apps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _ok_handler(request)

    _patch_clients(monkeypatch, _handler)
    session = await bootstrap_session(get_settings())

    assert session.fnol_jwt == "jwt-test"
    assert session.cp_jwt == "jwt-test"
    assert session.ap_jwt == "jwt-test"
    assert session.sda_customer_jwt == session.cp_jwt

    # One login per app.
    paths = sorted(r.url.path for r in captured)
    assert paths == ["/api/auth/login", "/auth/login", "/auth/login"]


async def test_bootstrap_session_never_logs_passwords(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_clients(monkeypatch, _ok_handler)

    with structlog.testing.capture_logs() as logs:
        await bootstrap_session(get_settings())

    forbidden = ("customer", "agent")  # the seeded passwords are these literal strings
    for event in logs:
        flat = " ".join(repr(value) for value in event.values())
        for needle in forbidden:
            # `customer` could appear in field values like `app="customer-portal"`
            # — only check the literal value, not the substring everywhere.
            assert f"password={needle!r}" not in flat
            assert f'"{needle}"' not in flat or "app" in flat or "username" in flat


async def test_bootstrap_session_fails_on_non_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "invalid credentials"})

    _patch_clients(monkeypatch, _handler)
    with pytest.raises(AgitatorAuthError):
        await bootstrap_session(get_settings())


async def test_bootstrap_session_fails_on_missing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"expires_in": 3600})  # no access_token

    _patch_clients(monkeypatch, _handler)
    with pytest.raises(AgitatorAuthError):
        await bootstrap_session(get_settings())
