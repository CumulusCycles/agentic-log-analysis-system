"""SSE streaming on POST /api/chat (Phase 7e PR 4b).

Verifies:
- `streaming=true` returns 200 + `text/event-stream`
- One `event: node` per node, ending with `event: complete`
- `complete` payload mirrors the non-streaming ChatResponse fields
- Pre-flight errors (auth, token cap) still return JSON, not SSE
- `streaming=false` and the default both use the JSON path unchanged
"""

from __future__ import annotations

import json

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from log_dashboard.auth.jwt import encode_token
from log_dashboard.config import get_settings
from log_dashboard.main import create_app


def _parse_sse_stream(body: str) -> list[tuple[str, dict]]:
    """Tiny SSE parser — enough for the events our route emits.

    Returns a list of (event_name, data_dict) tuples in stream order.
    """
    events: list[tuple[str, dict]] = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = ""
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        if event_name and data_lines:
            events.append((event_name, json.loads("".join(data_lines))))
    return events


@pytest.mark.asyncio
async def test_chat_streaming_true_returns_text_event_stream(
    client, valid_token, fail_if_real_llm_invoked
) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "hello", "streaming": True},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers.get("cache-control") == "no-cache"


@pytest.mark.asyncio
async def test_chat_streaming_emits_node_events_then_complete(
    client, valid_token, fail_if_real_llm_invoked
) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "what is wrong with fnol?", "streaming": True},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    events = _parse_sse_stream(response.text)

    # At least one node event (`ingest`) and exactly one terminal complete.
    node_events = [e for e in events if e[0] == "node"]
    complete_events = [e for e in events if e[0] == "complete"]
    assert len(node_events) >= 1, f"expected at least one node event, got {events!r}"
    assert len(complete_events) == 1, f"expected exactly one complete event, got {events!r}"
    # First node is always `ingest` (deterministic in dry-run + real-LLM paths).
    assert node_events[0][1]["node"] == "ingest"


@pytest.mark.asyncio
async def test_chat_streaming_complete_event_mirrors_chat_response_shape(
    client, valid_token, fail_if_real_llm_invoked
) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "test", "streaming": True},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    events = _parse_sse_stream(response.text)
    complete = next(e for e in events if e[0] == "complete")[1]

    # Same field names as ChatResponse — the two surfaces must not drift.
    assert "answer" in complete
    assert "citations" in complete
    assert "session_id" in complete
    assert "dry_run" in complete
    assert "tool_budget_exhausted" in complete

    # Settings default is dry-run → answer carries the canned marker.
    assert complete["dry_run"] is True
    assert "DRY_RUN" in complete["answer"]
    assert isinstance(complete["citations"], list)


@pytest.mark.asyncio
async def test_chat_streaming_dry_run_runs_full_graph_topology(
    client, valid_token, fail_if_real_llm_invoked
) -> None:
    """The dry-run model scripts a query_logs tool call so all 5 nodes fire.

    Hard-asserting the exact order keeps the SSE contract pinned — a future
    graph refactor that re-orders nodes would surface here before
    surprising the frontend.
    """
    response = await client.post(
        "/api/chat",
        json={"message": "describe recent errors", "streaming": True},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    events = _parse_sse_stream(response.text)
    node_order = [e[1]["node"] for e in events if e[0] == "node"]

    # Dry-run path: ingest → analyze (tool call) → correlate → predict
    # (no tool call) → respond. Exact sequence per `_DryRunChatModel`.
    assert node_order == [
        "ingest",
        "analyze",
        "correlate",
        "predict",
        "respond",
    ], f"unexpected node order: {node_order!r}"


@pytest.mark.asyncio
async def test_chat_streaming_over_token_cap_returns_json_413(
    monkeypatch: pytest.MonkeyPatch, fail_if_real_llm_invoked
) -> None:
    """Token-cap rejection fires BEFORE any SSE bytes are written.

    The client gets a clean JSON 413 — no half-open EventSource to manage.
    """
    monkeypatch.setenv("DASHBOARD_LLM_MAX_INPUT_TOKENS_PER_REQUEST", "512")
    get_settings.cache_clear()
    settings = get_settings()
    token = encode_token(username="admin", role="admin", settings=settings)

    huge_message = "the quick brown fox jumps over the lazy dog " * 60
    app = create_app()
    async with LifespanManager(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/chat",
                json={"message": huge_message, "streaming": True},
                headers={"Authorization": f"Bearer {token}"},
            )
    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/json")
    assert "exceeds input token cap" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_streaming_no_bearer_returns_json_401(client) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "hello", "streaming": True},
    )
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_chat_streaming_false_uses_json_path(
    client, valid_token, fail_if_real_llm_invoked
) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "hello", "streaming": False},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert "answer" in body
    assert body["dry_run"] is True


@pytest.mark.asyncio
async def test_chat_streaming_omitted_defaults_to_json(
    client, valid_token, fail_if_real_llm_invoked
) -> None:
    response = await client.post(
        "/api/chat",
        json={"message": "hello"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
