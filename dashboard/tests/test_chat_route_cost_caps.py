"""Cost-guard verification — token cap rejects oversized requests with 413."""

from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from log_dashboard.auth.jwt import encode_token
from log_dashboard.config import get_settings
from log_dashboard.main import create_app


async def _build_client_with_env(monkeypatch: pytest.MonkeyPatch, **env: str):
    """Construct a fresh app + client with the given env overrides.

    `monkeypatch.setenv` in the test body doesn't reach the `client` conftest
    fixture's cached app (the app + its agent graph are built during
    `LifespanManager` setup, BEFORE the test body runs). Tests that need
    Settings overrides build their own app here.
    """
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    settings = get_settings()
    token = encode_token(username="admin", role="admin", settings=settings)
    app = create_app()
    return app, settings, token


@pytest.mark.asyncio
async def test_chat_over_token_cap_returns_413(
    monkeypatch: pytest.MonkeyPatch, fail_if_real_llm_invoked
) -> None:
    """Use the minimum allowed cap (512) and a message known to exceed it.

    Phase 8 (ADR-017 §7) replaced the `tiktoken o200k_base` count with a
    `len(text) // 4` heuristic. The cap is enforced before any graph code
    runs, so `fail_if_real_llm_invoked` would never need to fire.
    """
    app, _, token = await _build_client_with_env(
        monkeypatch, DASHBOARD_LLM_MAX_INPUT_TOKENS_PER_REQUEST="512"
    )
    # ~2640 chars / 4 ≈ 660 estimated tokens — exceeds the 512 cap while
    # staying under ChatRequest.message's `max_length=4000`.
    huge_message = "the quick brown fox jumps over the lazy dog " * 60
    async with LifespanManager(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/chat",
                json={"message": huge_message},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert response.status_code == 413
    assert "exceeds input token cap" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_at_token_cap_is_allowed(client, valid_token, fail_if_real_llm_invoked) -> None:
    """Default cap (8000 tokens) admits a normal-length question."""
    response = await client.post(
        "/api/chat",
        json={"message": "what is wrong with fnol?"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_tool_budget_exhausted_flag(
    monkeypatch: pytest.MonkeyPatch, fail_if_real_llm_invoked
) -> None:
    """A tool-budget of 1 means the first correlate flip leaves budget=0;
    the response surfaces `tool_budget_exhausted=true`."""
    app, _, token = await _build_client_with_env(
        monkeypatch, DASHBOARD_LLM_MAX_TOOL_CALLS_PER_REQUEST="1"
    )
    async with LifespanManager(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/chat",
                json={"message": "what is wrong?"},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert response.status_code == 200
    body = response.json()
    # Dry-run flow runs exactly one correlate → budget goes 1 → 0 → exhausted=True
    assert body["tool_budget_exhausted"] is True
