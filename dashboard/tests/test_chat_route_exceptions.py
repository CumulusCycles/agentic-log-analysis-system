"""Router-level tests for non-LLM exception paths.

Phase 8 / ADR-017 narrowed `is_llm_api_error` from `httpx.HTTPError` (the
base class) to a specific set of transport-failure subclasses. With the
narrowed catch, exceptions that USED to be mapped to 502 ("upstream LLM
unavailable") now bubble through to the global 500 handler. These tests
pin that behaviour so a future widening of the catch can't silently
re-mask programming errors as upstream failures.

Two routes exercise `is_llm_api_error`:
- `POST /api/chat` — both streaming and non-streaming paths
- `GET /api/errors/{id}` — Error Detail + Suggested Fix

We use `monkeypatch` to inject a graph that raises `ValueError` (a
non-LLM exception) and assert the response is 500, not 502.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from langchain_core.documents import Document

from log_dashboard.ingest.embeddings import make_doc_id


class _BoomGraph:
    """Stand-in for a compiled LangGraph whose `ainvoke` raises a
    non-LLM exception. Used to drive the routers down the 500 path.
    """

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def ainvoke(self, *args, **kwargs):  # noqa: ARG002
        raise self._exc

    async def astream(self, *args, **kwargs):  # noqa: ARG002
        raise self._exc
        # Generator semantics — `yield` is unreachable but flags this
        # as an async generator for the caller's `async for` loop.
        yield  # type: ignore[unreachable]

    async def aget_state(
        self, *args, **kwargs
    ):  # noqa: ARG002 — not reached because astream raises first
        return None


@pytest.mark.asyncio
async def test_chat_returns_500_when_graph_raises_non_llm_exception(
    client, valid_token, monkeypatch
) -> None:
    """A `ValueError` from inside `graph.ainvoke` must NOT be mapped to
    502. With the narrowed `is_llm_api_error`, only specific httpx
    transport failures + `ollama.ResponseError` qualify; everything else
    bubbles to the global 500 handler."""
    boom = _BoomGraph(ValueError("not an LLM error"))

    # The client fixture's lifespan already built the real graph; swap
    # `app.state.agent_graph` for our raising stub before making the call.
    # The `client` fixture wraps `app_instance` whose app is on
    # `client._transport.app` — pull it from the AsyncClient's transport.
    app = client._transport.app  # noqa: SLF001 — internal access fine in tests
    monkeypatch.setattr(app.state, "agent_graph", boom)

    response = await client.post(
        "/api/chat",
        json={"message": "hello"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_chat_still_returns_502_for_real_llm_transport_error(
    client, valid_token, monkeypatch
) -> None:
    """Belt-and-braces sibling of the test above — confirms the 502 path
    isn't accidentally broken by the narrowing. An `httpx.ConnectError`
    DOES match `is_llm_api_error` and should surface as 502, not 500."""
    import httpx

    boom = _BoomGraph(httpx.ConnectError("ollama unreachable"))
    app = client._transport.app  # noqa: SLF001
    monkeypatch.setattr(app.state, "agent_graph", boom)

    response = await client.post(
        "/api/chat",
        json={"message": "hello"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 502
    assert "upstream LLM" in response.json()["detail"]


@pytest_asyncio.fixture
async def errors_client_with_chroma(monkeypatch, fake_vectorstore):
    """Variant of `client_with_chroma` from `test_errors_route.py` — but
    we additionally swap `app.state.agent_graph` after lifespan so the
    /api/errors/{id} route hits a raising graph.
    """
    from log_dashboard import main as main_module

    monkeypatch.setattr(main_module, "is_embeddings_disabled", lambda _settings: False)
    monkeypatch.setattr(main_module, "build_vectorstore", lambda _settings, **_kw: fake_vectorstore)
    monkeypatch.setattr(main_module, "run_initial_backfill", lambda *_args, **_kw: [])

    from log_dashboard.main import create_app

    app = create_app()
    async with LifespanManager(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac, app, fake_vectorstore


def _seed_error_entry(store, raw: str = "ERROR fnol request_failed status=500") -> str:
    doc_id = make_doc_id("fnol", raw)
    store.add_documents(
        documents=[
            Document(
                page_content=raw,
                metadata={
                    "id": doc_id,
                    "app": "fnol",
                    "level": "ERROR",
                    "event": "request_failed",
                    "source": "prod",
                    "timestamp_iso": "2026-06-05T10:00:00+00:00",
                    "raw": raw,
                },
            )
        ],
        ids=[doc_id],
    )
    return doc_id


@pytest.mark.asyncio
async def test_errors_returns_500_when_graph_raises_non_llm_exception(
    errors_client_with_chroma, valid_token, monkeypatch
) -> None:
    """Same contract as the chat-route test: a non-LLM exception from
    `graph.ainvoke` bubbles to 500. Mirrors the narrowed
    `is_llm_api_error` catch in `routers/errors.py`."""
    ac, app, store = errors_client_with_chroma
    doc_id = _seed_error_entry(store)
    monkeypatch.setattr(app.state, "agent_graph", _BoomGraph(ValueError("not LLM")))

    response = await ac.get(
        f"/api/errors/{doc_id}",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_errors_still_returns_502_for_real_llm_transport_error(
    errors_client_with_chroma, valid_token, monkeypatch
) -> None:
    """Sibling: confirms the errors route's 502 path is intact."""
    import httpx

    ac, app, store = errors_client_with_chroma
    doc_id = _seed_error_entry(store)
    monkeypatch.setattr(app.state, "agent_graph", _BoomGraph(httpx.ReadTimeout("ollama slow")))

    response = await ac.get(
        f"/api/errors/{doc_id}",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 502
    assert "upstream LLM" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Streaming path on /api/chat — same is_llm_api_error classifier fires
# inside `_stream_chat_events`, so the SSE error-event emit needs the
# same regression guard as the non-streaming JSON path.
# ---------------------------------------------------------------------------


def _decode_sse_events(body: bytes) -> list[dict[str, str]]:
    """Parse the SSE wire format into a list of {event, data} dicts.

    Minimal — the streaming endpoint only emits `event: <name>\\ndata: <json>\\n\\n`
    so we don't need a full SSE parser, just a splitter on the blank
    line that delimits events.
    """
    events: list[dict[str, str]] = []
    for chunk in body.decode("utf-8").split("\n\n"):
        chunk = chunk.strip()
        if not chunk:
            continue
        ev: dict[str, str] = {}
        for line in chunk.splitlines():
            key, _, value = line.partition(": ")
            ev[key] = value
        events.append(ev)
    return events


@pytest.mark.asyncio
async def test_chat_streaming_emits_generic_error_for_non_llm_exception(
    client, valid_token, monkeypatch
) -> None:
    """When `streaming=true` and the graph raises a non-LLM exception
    (e.g., ValueError from a buggy tool path), `_stream_chat_events`
    must NOT label it as "upstream LLM unavailable" — that detail is
    reserved for the LLM-transport-error branch. The generic
    `stream failed unexpectedly` detail covers everything else."""
    boom = _BoomGraph(ValueError("not an LLM error"))
    app = client._transport.app  # noqa: SLF001
    monkeypatch.setattr(app.state, "agent_graph", boom)

    response = await client.post(
        "/api/chat",
        json={"message": "hello", "streaming": True},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    # Pre-flight passes (auth + token cap), then the stream starts.
    # The error surfaces as an SSE `event: error` payload, not a 500
    # — the stream is already open by the time the graph raises.
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _decode_sse_events(response.content)
    error_events = [e for e in events if e.get("event") == "error"]
    assert len(error_events) == 1
    detail = error_events[0]["data"]
    assert (
        "upstream LLM" not in detail
    ), "non-LLM exceptions must not be mis-labeled as LLM-transport failures"
    assert "stream failed" in detail


@pytest.mark.asyncio
async def test_chat_streaming_emits_upstream_llm_error_for_real_transport_error(
    client, valid_token, monkeypatch
) -> None:
    """Sibling: the SSE error-event path correctly labels real LLM
    transport failures (httpx.ConnectError) with the "upstream LLM
    unavailable" copy. Regression guard so the narrowed
    `is_llm_api_error` doesn't close this path."""
    import httpx

    boom = _BoomGraph(httpx.ConnectError("ollama unreachable"))
    app = client._transport.app  # noqa: SLF001
    monkeypatch.setattr(app.state, "agent_graph", boom)

    response = await client.post(
        "/api/chat",
        json={"message": "hello", "streaming": True},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _decode_sse_events(response.content)
    error_events = [e for e in events if e.get("event") == "error"]
    assert len(error_events) == 1
    detail = error_events[0]["data"]
    assert "upstream LLM" in detail
