"""Auth surface for POST /api/chat.

Mirrors the auth checks from the other admin-protected routes; the goal is
to confirm `Depends(get_current_admin)` is wired correctly and that the
"missing bearer token" branch returns 401 before any graph code runs.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_chat_no_bearer_returns_401(client) -> None:
    response = await client.post("/api/chat", json={"message": "hello"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_bad_bearer_returns_401(client) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "hello"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_valid_bearer_returns_200(client, valid_token) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "hello"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "answer" in body
    assert "session_id" in body
    assert body["dry_run"] is True  # Settings default is safe-by-default
