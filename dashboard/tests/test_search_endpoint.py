"""Tests for POST /api/logs/search — the Phase 7d semantic-search endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from log_dashboard.ingest.vectorstore import upsert_entries
from log_dashboard.schemas import LogEntry, LogLevel

_NOW = datetime(2026, 6, 4, 12, 0, 0, tzinfo=UTC)


def _entry(
    seq: int,
    *,
    app: str = "fnol",
    level: LogLevel = LogLevel.INFO,
    event: str = "claim_submitted",
    ago_sec: int = 0,
) -> LogEntry:
    return LogEntry(
        id=f"{app}:{seq}",
        timestamp=_NOW - timedelta(seconds=ago_sec),
        level=level,
        app=app,
        event=event,
        fields={"seq": seq},
        raw=f'{{"event":"{event}","seq":{seq}}}',
    )


def _seed_vectorstore(store, entries: list[LogEntry]) -> None:
    upsert_entries(store, entries)


@pytest.fixture
def ready_app(app_instance, fake_vectorstore):
    """Lifespan ran in embeddings-disabled mode (no OPENAI_API_KEY in test env).
    Inject a pre-seeded fake vectorstore so the search endpoint behaves as if
    embeddings were configured."""
    _seed_vectorstore(
        fake_vectorstore,
        [
            _entry(0, event="claim_submitted"),
            _entry(1, level=LogLevel.ERROR, event="unhandled_exception"),
            _entry(2, app="agent-portal", event="sda_upstream_rejected"),
            _entry(3, app="customer-portal", level=LogLevel.WARN, event="sda_upstream_unreachable"),
        ],
    )
    app_instance.state.vectorstore = fake_vectorstore
    return app_instance


async def test_search_requires_auth(client) -> None:
    response = await client.post("/api/logs/search", json={"query": "anything"})
    assert response.status_code == 401


async def test_search_returns_503_when_embeddings_disabled(client, valid_token) -> None:
    # Default lifespan path: OPENAI_API_KEY is not in the test env, so
    # is_embeddings_disabled() short-circuits and app.state.vectorstore is None.
    response = await client.post(
        "/api/logs/search",
        json={"query": "auth failures"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


async def test_search_returns_entries_with_scores(client, valid_token, ready_app) -> None:
    response = await client.post(
        "/api/logs/search",
        json={"query": "claim submitted", "top_k": 4},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["entries"]) == 4
    assert len(body["scores"]) == 4
    # Scores are floats. Order matters (highest similarity first per Chroma
    # default) but values are stub-derived so we don't assert magnitudes.
    assert all(isinstance(s, float) for s in body["scores"])
    # Each returned entry maintains the LogEntry shape.
    first = body["entries"][0]
    assert {"id", "timestamp", "level", "app", "event", "fields", "raw"} <= set(first)


async def test_search_filters_to_a_single_app(client, valid_token, ready_app) -> None:
    response = await client.post(
        "/api/logs/search",
        json={"query": "anything", "apps": ["fnol"], "top_k": 10},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["entries"]
    assert {e["app"] for e in body["entries"]} == {"fnol"}


async def test_search_filters_by_level(client, valid_token, ready_app) -> None:
    response = await client.post(
        "/api/logs/search",
        json={"query": "anything", "levels": ["ERROR", "WARN"], "top_k": 10},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["entries"]
    assert all(e["level"] in ("ERROR", "WARN") for e in body["entries"])


async def test_search_rejects_unknown_app_with_422(client, valid_token, ready_app) -> None:
    response = await client.post(
        "/api/logs/search",
        json={"query": "x", "apps": ["nonexistent-app"]},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 422
    assert "unknown app" in response.json()["detail"]
