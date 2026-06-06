"""Tests for `GET /api/chroma/stats`.

Builds the real FastAPI app, injects a `fake_vectorstore` onto
`app.state`, and exercises the aggregations end-to-end. Uses
`upsert_entries()` (the same function the production ingest pipeline
uses) so the metadata layout under test matches what watcher + backfill
actually write.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio

from log_dashboard.ingest.vectorstore import upsert_entries
from log_dashboard.schemas import LogEntry, LogLevel


def _entry(
    *,
    app: str,
    level: LogLevel,
    event: str,
    source: str = "prod",
    timestamp: datetime | None = None,
    raw_suffix: str = "",
) -> LogEntry:
    """Build a minimal LogEntry. `raw_suffix` keeps content-hash IDs distinct
    when the same (app, event, level, source) shows up multiple times."""
    ts = timestamp or datetime.now(tz=UTC)
    raw = (
        f'{{"app":"{app}","level":"{level.value}","event":"{event}",'
        f'"source":"{source}","ts":"{ts.isoformat()}","extra":"{raw_suffix}"}}'
    )
    return LogEntry(
        id=f"{app}:{raw_suffix or 'x'}",
        timestamp=ts,
        level=level,
        app=app,
        event=event,
        fields={},
        raw=raw,
        source=source,
    )


@pytest_asyncio.fixture
async def stats_url() -> str:
    return "/api/chroma/stats"


async def test_stats_401_without_jwt(client, stats_url) -> None:
    """Anonymous requests are rejected (matches every other admin-gated route)."""
    response = await client.get(stats_url)
    assert response.status_code == 401


async def test_stats_503_when_vectorstore_unavailable(
    app_instance, client, valid_token, stats_url
) -> None:
    """Degraded mode (no OpenAI key → app.state.vectorstore is None) → 503."""
    app_instance.state.vectorstore = None
    response = await client.get(stats_url, headers={"Authorization": f"Bearer {valid_token}"})
    assert response.status_code == 503
    assert "Vectorstore unavailable" in response.json()["detail"]


async def test_stats_empty_corpus_returns_zeros_with_model_info(
    app_instance, client, valid_token, fake_vectorstore, stats_url
) -> None:
    """Empty vectorstore returns total=0 + empty breakdowns + populated model+dimensions."""
    app_instance.state.vectorstore = fake_vectorstore
    response = await client.get(stats_url, headers={"Authorization": f"Bearer {valid_token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 0
    assert body["by_app"] == {}
    assert body["by_level"] == {}
    assert body["by_source"] == {}
    assert body["by_event"] == []
    # by_day still has the full 30-day window with zeros so the chart x-axis
    # is continuous on the frontend.
    assert len(body["by_day"]) == 30
    assert all(d["count"] == 0 for d in body["by_day"])
    # Model metadata is always populated.
    assert body["embedding_model"]
    assert body["dimensions"] == 1536
    assert body["as_of"]


async def test_stats_by_app_and_level_breakdown_matches_inserted_data(
    app_instance, client, valid_token, fake_vectorstore, stats_url
) -> None:
    """Insert known mix; assert by_app + by_level counts are exact."""
    entries = (
        [
            _entry(app="fnol", level=LogLevel.WARN, event="login_failed", raw_suffix=f"f{i}")
            for i in range(3)
        ]
        + [
            _entry(
                app="shared-data-api",
                level=LogLevel.ERROR,
                event="chaos_honored",
                raw_suffix=f"s{i}",
            )
            for i in range(2)
        ]
        + [
            _entry(
                app="customer-portal", level=LogLevel.WARN, event="chaos_honored", raw_suffix="cp1"
            ),
        ]
    )
    upsert_entries(fake_vectorstore, entries)
    app_instance.state.vectorstore = fake_vectorstore

    response = await client.get(stats_url, headers={"Authorization": f"Bearer {valid_token}"})
    body = response.json()
    assert body["total_count"] == 6
    assert body["by_app"] == {"fnol": 3, "shared-data-api": 2, "customer-portal": 1}
    assert body["by_level"] == {"WARN": 4, "ERROR": 2}


async def test_stats_by_source_buckets_unknown_for_missing_source(
    app_instance, client, valid_token, fake_vectorstore, stats_url
) -> None:
    """Entries with `source="prod"` AND `source="synthetic"` bucket cleanly;
    a metadata row with no source falls back to "unknown" (defensive — every
    LogEntry has source=prod by default, but the helper handles missing keys)."""
    entries = [
        _entry(app="fnol", level=LogLevel.WARN, event="x", source="prod", raw_suffix="p1"),
        _entry(app="fnol", level=LogLevel.WARN, event="x", source="prod", raw_suffix="p2"),
        _entry(app="fnol", level=LogLevel.WARN, event="x", source="synthetic", raw_suffix="s1"),
    ]
    upsert_entries(fake_vectorstore, entries)
    app_instance.state.vectorstore = fake_vectorstore

    response = await client.get(stats_url, headers={"Authorization": f"Bearer {valid_token}"})
    body = response.json()
    assert body["by_source"] == {"prod": 2, "synthetic": 1}


async def test_stats_by_event_returns_top_10_descending(
    app_instance, client, valid_token, fake_vectorstore, stats_url
) -> None:
    """by_event is capped at 10 entries, sorted by count descending."""
    # 12 distinct event names with descending frequencies (12, 11, ..., 1).
    entries = []
    for n in range(12, 0, -1):
        for i in range(n):
            entries.append(
                _entry(
                    app="fnol",
                    level=LogLevel.WARN,
                    event=f"event-{n:02d}",
                    raw_suffix=f"e{n}-{i}",
                )
            )
    upsert_entries(fake_vectorstore, entries)
    app_instance.state.vectorstore = fake_vectorstore

    response = await client.get(stats_url, headers={"Authorization": f"Bearer {valid_token}"})
    body = response.json()
    assert len(body["by_event"]) == 10
    # Counts strictly descending.
    counts = [row["count"] for row in body["by_event"]]
    assert counts == sorted(counts, reverse=True)
    # Top entry is event-12 with 12 occurrences.
    assert body["by_event"][0] == {"event": "event-12", "count": 12}


async def test_stats_by_day_buckets_by_utc_date_and_includes_zero_days(
    app_instance, client, valid_token, fake_vectorstore, stats_url
) -> None:
    """Two entries today + one 5 days ago. Expect 30-day window with counts
    in the right buckets and zeros elsewhere (continuous x-axis for chart)."""
    now = datetime.now(tz=UTC)
    five_days_ago = now - timedelta(days=5)
    entries = [
        _entry(app="fnol", level=LogLevel.WARN, event="a", timestamp=now, raw_suffix="t1"),
        _entry(app="fnol", level=LogLevel.WARN, event="a", timestamp=now, raw_suffix="t2"),
        _entry(
            app="fnol", level=LogLevel.WARN, event="a", timestamp=five_days_ago, raw_suffix="t3"
        ),
    ]
    upsert_entries(fake_vectorstore, entries)
    app_instance.state.vectorstore = fake_vectorstore

    response = await client.get(stats_url, headers={"Authorization": f"Bearer {valid_token}"})
    body = response.json()
    by_day = {row["date"]: row["count"] for row in body["by_day"]}
    # 30 day series, today on the end, ascending.
    assert len(body["by_day"]) == 30
    assert body["by_day"][-1]["date"] == now.strftime("%Y-%m-%d")
    assert by_day[now.strftime("%Y-%m-%d")] == 2
    assert by_day[five_days_ago.strftime("%Y-%m-%d")] == 1


async def test_stats_by_day_excludes_entries_older_than_30_days(
    app_instance, client, valid_token, fake_vectorstore, stats_url
) -> None:
    """A 60-day-old entry doesn't pollute the by_day total."""
    now = datetime.now(tz=UTC)
    sixty_days_ago = now - timedelta(days=60)
    entries = [
        _entry(app="fnol", level=LogLevel.WARN, event="a", timestamp=now, raw_suffix="recent"),
        _entry(
            app="fnol", level=LogLevel.WARN, event="a", timestamp=sixty_days_ago, raw_suffix="old"
        ),
    ]
    upsert_entries(fake_vectorstore, entries)
    app_instance.state.vectorstore = fake_vectorstore

    response = await client.get(stats_url, headers={"Authorization": f"Bearer {valid_token}"})
    body = response.json()
    # The old entry is in total_count but not in by_day (which is the 30-day window).
    assert body["total_count"] == 2
    by_day_total = sum(row["count"] for row in body["by_day"])
    assert by_day_total == 1
