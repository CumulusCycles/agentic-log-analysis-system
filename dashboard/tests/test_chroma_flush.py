"""Tests for `POST /api/chroma/flush`.

JWT gating, 503 when no store, no-op on empty corpus, full wipe on a
populated corpus, and repeat-flush idempotency.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest_asyncio

from log_dashboard.ingest.vectorstore import upsert_entries
from log_dashboard.schemas import LogEntry, LogLevel


def _entry(*, raw_suffix: str) -> LogEntry:
    ts = datetime.now(tz=UTC)
    return LogEntry(
        id=f"fnol:{raw_suffix}",
        timestamp=ts,
        level=LogLevel.WARN,
        app="fnol",
        event="event",
        fields={},
        raw=f'{{"app":"fnol","level":"WARN","event":"e","extra":"{raw_suffix}"}}',
        source="prod",
    )


@pytest_asyncio.fixture
async def flush_url() -> str:
    return "/api/chroma/flush"


async def test_flush_401_without_jwt(client, flush_url) -> None:
    response = await client.post(flush_url)
    assert response.status_code == 401


async def test_flush_503_when_vectorstore_unavailable(
    app_instance, client, valid_token, flush_url
) -> None:
    app_instance.state.vectorstore = None
    response = await client.post(flush_url, headers={"Authorization": f"Bearer {valid_token}"})
    assert response.status_code == 503
    assert "Vectorstore unavailable" in response.json()["detail"]


async def test_flush_empty_corpus_returns_zero(
    app_instance, client, valid_token, fake_vectorstore, flush_url
) -> None:
    """No docs to delete — the endpoint succeeds and reports 0."""
    app_instance.state.vectorstore = fake_vectorstore
    response = await client.post(flush_url, headers={"Authorization": f"Bearer {valid_token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["deleted_count"] == 0
    assert body["as_of"]
    # Still empty after the no-op.
    assert fake_vectorstore._collection.count() == 0


async def test_flush_wipes_populated_corpus(
    app_instance, client, valid_token, fake_vectorstore, flush_url
) -> None:
    """Insert several entries, flush, verify count goes to zero and the
    reported `deleted_count` matches the pre-flush total."""
    entries = [_entry(raw_suffix=f"e{i}") for i in range(7)]
    upsert_entries(fake_vectorstore, entries)
    assert fake_vectorstore._collection.count() == 7
    app_instance.state.vectorstore = fake_vectorstore

    response = await client.post(flush_url, headers={"Authorization": f"Bearer {valid_token}"})
    assert response.status_code == 200
    assert response.json()["deleted_count"] == 7
    assert fake_vectorstore._collection.count() == 0


async def test_flush_is_idempotent(
    app_instance, client, valid_token, fake_vectorstore, flush_url
) -> None:
    """A second flush on the now-empty corpus reports 0 (no error)."""
    upsert_entries(fake_vectorstore, [_entry(raw_suffix="only")])
    app_instance.state.vectorstore = fake_vectorstore

    first = await client.post(flush_url, headers={"Authorization": f"Bearer {valid_token}"})
    assert first.json()["deleted_count"] == 1

    second = await client.post(flush_url, headers={"Authorization": f"Bearer {valid_token}"})
    assert second.status_code == 200
    assert second.json()["deleted_count"] == 0


async def test_flush_subsequent_stats_call_reflects_empty(
    app_instance, client, valid_token, fake_vectorstore, flush_url
) -> None:
    """The most important user-visible promise: after flush, the
    `/api/chroma/stats` page shows zeros across the board."""
    upsert_entries(fake_vectorstore, [_entry(raw_suffix="x"), _entry(raw_suffix="y")])
    app_instance.state.vectorstore = fake_vectorstore

    await client.post(flush_url, headers={"Authorization": f"Bearer {valid_token}"})

    stats = await client.get(
        "/api/chroma/stats", headers={"Authorization": f"Bearer {valid_token}"}
    )
    body = stats.json()
    assert body["total_count"] == 0
    assert body["by_app"] == {}
    assert body["by_level"] == {}
