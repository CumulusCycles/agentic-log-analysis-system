"""Forward-compatibility check — `streaming=true` is rejected with 422.

PR 4a returns JSON only. Clients should pass `streaming=false` (default).
PR 4b will flip the rejection to a real SSE handler without changing the
request schema, so this assertion will need to update at that time.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_chat_streaming_true_returns_422(client, valid_token) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "hello", "streaming": True},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 422
    assert "streaming" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_chat_streaming_false_is_accepted(client, valid_token) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "hello", "streaming": False},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_streaming_omitted_defaults_to_false(client, valid_token) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "hello"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
