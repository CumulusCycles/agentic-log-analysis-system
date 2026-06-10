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
    """Lifespan ran in embeddings-disabled mode (Ollama unreachable in test env).
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


async def test_search_returns_503_when_embeddings_unreachable(client, valid_token) -> None:
    # Default lifespan path: Ollama is unreachable in the test env (probe URL
    # points at a closed port), so embeddings_state() returns "unreachable"
    # and app.state.vectorstore is None.
    response = await client.post(
        "/api/logs/search",
        json={"query": "auth failures"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 503
    assert "OLLAMA_BASE_URL" in response.json()["detail"]


async def test_search_returns_503_with_warming_up_detail_during_loading(
    client, valid_token, app_instance
) -> None:
    """v1.1.2 Option A round-4 — the search router picks one of two
    distinct 503 detail strings based on `embeddings_state`. The
    `loading` path returns a "warming up — try again in a minute"
    message so the frontend can distinguish the cold-deploy window from
    a genuine "URL unreachable" config error. Pin both paths so a typo
    in the detail string or an inverted branch wouldn't silently pass.
    """
    # Manually flip the lifespan-set value to "loading". Vectorstore
    # stays None, so the router enters the 503 branch — but now picks
    # the loading-specific detail.
    app_instance.state.embeddings_state = "loading"
    response = await client.post(
        "/api/logs/search",
        json={"query": "anything"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "warming up" in detail
    assert "OLLAMA_BASE_URL" not in detail


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


async def test_search_response_partial_corpus_false_when_backfill_complete(
    client, valid_token, ready_app
) -> None:
    """v1.1.2 — when the lifespan backfill task has finished (the normal
    steady-state), the response field `partial_corpus` MUST be False so
    operators reading the API don't see a misleading 'still indexing' hint.
    """
    ready_app.state.backfill_complete = True
    response = await client.post(
        "/api/logs/search",
        json={"query": "claim", "top_k": 4},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    assert response.json()["partial_corpus"] is False


async def test_search_response_partial_corpus_true_during_backfill(
    client, valid_token, ready_app
) -> None:
    """v1.1.2 — during the initial backfill window the response surfaces
    `partial_corpus: True` so the frontend can distinguish 'no matches'
    from 'still indexing'. The flag reads `app.state.backfill_complete`
    via `getattr` with a False default (per the v1.1.2 round-1 flip);
    this test pins the False transition explicitly.
    """
    ready_app.state.backfill_complete = False
    response = await client.post(
        "/api/logs/search",
        json={"query": "claim", "top_k": 4},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["partial_corpus"] is True
    # Behaviour-preserving: the entries+scores arrays still come back
    # populated — partial corpus does NOT block search.
    assert len(body["entries"]) >= 1
    assert len(body["scores"]) == len(body["entries"])


async def test_search_response_partial_corpus_defaults_true_when_flag_unset(
    client, valid_token, ready_app
) -> None:
    """v1.1.2 post-review — pin the `getattr(..., False)` default
    explicitly. Without this test, a typo or future refactor that
    flipped the default back to `True` would silently regress (the
    "missing flag in production → silent degraded mode" hole that
    motivated the round-1 flip).

    The `ready_app` fixture from `_seed_vectorstore` does not set
    `backfill_complete` (it only assigns `vectorstore`). The lifespan
    DID set it (False on entry), but `delattr` ensures the attribute
    is absent so the getattr default path actually runs.
    """
    if hasattr(ready_app.state, "backfill_complete"):
        delattr(ready_app.state, "backfill_complete")

    response = await client.post(
        "/api/logs/search",
        json={"query": "claim", "top_k": 4},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    # Missing flag → safer default → partial_corpus must be True
    # ("still indexing"), not the previous unsafe False.
    assert response.json()["partial_corpus"] is True
