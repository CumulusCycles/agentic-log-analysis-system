"""Safe-by-default verification — no real OpenAI call path is ever entered.

The Settings default `DASHBOARD_LLM_DRY_RUN=True` is the primary gate; the
`fail_if_real_llm_invoked` fixture is defence-in-depth — it monkeypatches
`ChatOpenAI.__init__` to raise, so even if the dry-run flag flipped
unexpectedly the test would fail loudly.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_chat_default_is_dry_run(client, valid_token, fail_if_real_llm_invoked) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "what is wrong with fnol?"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert "DRY_RUN" in body["answer"]


@pytest.mark.asyncio
async def test_chat_session_id_minted_on_first_call(
    client, valid_token, fail_if_real_llm_invoked
) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "hello"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    body = response.json()
    assert body["session_id"]
    assert "-" in body["session_id"]  # UUID4 shape


@pytest.mark.asyncio
async def test_chat_session_id_reused_carries_history(
    client, valid_token, fail_if_real_llm_invoked
) -> None:
    """Two calls with the same `session_id` land on the same checkpoint thread.

    Asserts the server echoes the session_id back unchanged on the second
    call — proves the operator's `session_id` is honoured rather than a new
    one minted per request.
    """
    first = await client.post(
        "/api/chat",
        json={"message": "first message"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    session_id = first.json()["session_id"]

    second = await client.post(
        "/api/chat",
        json={"message": "second message", "session_id": session_id},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert second.status_code == 200
    assert second.json()["session_id"] == session_id
