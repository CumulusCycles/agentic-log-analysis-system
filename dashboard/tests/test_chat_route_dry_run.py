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


@pytest.mark.asyncio
async def test_chat_complete_log_carries_duration_ms(
    client, valid_token, fail_if_real_llm_invoked, caplog
) -> None:
    """v1.1.1 telemetry: the `chat_complete` log event MUST include a
    `duration_ms` integer field. Without this, operators have no
    structured way to spot cold-start regressions or latency cliffs
    (e.g. a future qwen2.5:14b trial running 3-4x slower than llama3.1).

    Asserts presence + sanity (>= 0). The exact value depends on
    machine speed; dry-run graphs typically land in single-digit ms.

    structlog collapses the whole event dict into the LogRecord's
    message string. Under pytest caplog the renderer emits a Python
    dict repr (single quotes), so we use `ast.literal_eval` rather than
    `json.loads` to recover the structured payload.
    """
    import ast
    import logging

    caplog.set_level(logging.INFO, logger="chat")

    response = await client.post(
        "/api/chat",
        json={"message": "hello"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200

    chat_complete_payloads: list[dict] = []
    for rec in caplog.records:
        try:
            payload = ast.literal_eval(rec.getMessage())
        except (ValueError, SyntaxError):
            continue
        if isinstance(payload, dict) and payload.get("event") == "chat_complete":
            chat_complete_payloads.append(payload)

    assert len(chat_complete_payloads) == 1, "expected exactly one chat_complete log"
    duration = chat_complete_payloads[0].get("duration_ms")
    assert duration is not None, "chat_complete must carry a duration_ms field"
    assert isinstance(duration, int)
    # v1.1.2 — `max(1, round(...))` guarantees a measured operation always
    # reports at least 1ms; 0 is now reserved for "not measured". Drop the
    # weaker `>= 0` from v1.1.1 — that bound silently allowed `int()`
    # floor-truncation on sub-ms dry-run paths to look like missing data.
    assert duration >= 1
