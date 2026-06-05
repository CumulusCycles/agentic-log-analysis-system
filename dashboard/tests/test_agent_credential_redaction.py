"""Defence-in-depth: credentials never reach LangSmith / response / LLM context.

Three layers exercised:
1. User-input sanitisation — a Bearer / JWT / DSN in the chat message is
   redacted before the graph state contains the secret.
2. Tool-output sanitisation — a log line whose `raw` carries a JWT-shaped
   token is redacted by `query_logs` before the cited entry returns.
3. Response shape — the final `ChatResponse` never contains the secret in
   `answer` or `citations[*].raw`.
"""

from __future__ import annotations

import json

import pytest
from langchain_core.documents import Document

_FORBIDDEN_TOKENS = (
    "ghp_abcdefghijklmnopqrstuvwxyz",
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbGljZSJ9.signature_segment_at_least_20_chars",
    "secretdbpassword",
    "fnol_app_api_key_change_me",
)


def _assert_no_forbidden(blob: str) -> None:
    for needle in _FORBIDDEN_TOKENS:
        assert needle not in blob, f"forbidden token {needle!r} leaked in {blob[:200]!r}"


@pytest.mark.asyncio
async def test_user_input_bearer_redacted_before_response(client, valid_token) -> None:
    """Operator pastes a Bearer token by accident — neither the answer nor
    any echo of the message in the response carries the raw token."""
    response = await client.post(
        "/api/chat",
        json={
            "message": (
                "investigate this: Bearer ghp_abcdefghijklmnopqrstuvwxyz" " — what happened?"
            )
        },
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    serialised = json.dumps(response.json())
    _assert_no_forbidden(serialised)


@pytest.mark.asyncio
async def test_user_input_jwt_redacted(client, valid_token) -> None:
    response = await client.post(
        "/api/chat",
        json={
            "message": (
                "the JWT was eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbGljZSJ9."
                "signature_segment_at_least_20_chars"
            )
        },
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    _assert_no_forbidden(json.dumps(response.json()))


@pytest.mark.asyncio
async def test_user_input_dsn_redacted(client, valid_token) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "tried postgres://postgres:secretdbpassword@postgres:5432/insurance"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    _assert_no_forbidden(json.dumps(response.json()))


@pytest.mark.asyncio
async def test_user_input_api_key_redacted(client, valid_token) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "X-API-Key: fnol_app_api_key_change_me did not work"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    _assert_no_forbidden(json.dumps(response.json()))


@pytest.mark.asyncio
async def test_tool_output_log_with_secret_redacted_in_citations(
    agent_graph, fake_vectorstore
) -> None:
    """A log line whose `raw` carries a JWT slips past the per-app audit;
    `query_logs` sanitises it before the citation reaches the LLM context
    and the response body."""
    from langchain_core.messages import HumanMessage

    fake_vectorstore.add_documents(
        documents=[
            Document(
                page_content="auth got JWT",
                metadata={
                    "id": "auth:leak-1",
                    "app": "shared-data-api",
                    "level": "ERROR",
                    "event": "auth_failed",
                    "timestamp_iso": "2026-06-05T10:00:00+00:00",
                    "raw": (
                        "ERROR auth got token "
                        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbGljZSJ9."
                        "signature_segment_at_least_20_chars"
                    ),
                },
            )
        ],
        ids=["auth:leak-1"],
    )
    result = await agent_graph.ainvoke(
        {
            "messages": [HumanMessage(content="auth failure?")],
            "session_id": "sess-leak",
            "jwt_sub": "admin",
            "citations": [],
            "dry_run": True,
            "tool_budget_remaining": 4,
            "tool_budget_exhausted": False,
        },
        config={"configurable": {"thread_id": "admin:sess-leak"}},
    )
    # Inspect every message in state — even the ToolMessage's raw payload.
    all_content = " ".join(str(m.content) for m in result["messages"])
    _assert_no_forbidden(all_content)
    # And the harvested citations.
    for c in result["citations"]:
        _assert_no_forbidden(c.raw)


@pytest.mark.asyncio
async def test_log_line_credentials_not_in_response_body(client, valid_token) -> None:
    """End-to-end: a leaky log + a clean question → the secret never appears
    anywhere in the JSON response."""
    response = await client.post(
        "/api/chat",
        json={"message": "what is wrong?"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    _assert_no_forbidden(json.dumps(response.json()))
