"""Tests for the WARN+ERROR / source=prod / dry-run ingest gate.

Verifies that:
  - The `filter_for_ingest` helper applies both level AND source predicates.
  - `parse_*_line` derives `source="health"` for healthcheck requests and
    `source="prod"` for everything else, and honours an explicit `source`
    field if a future cross-app PR starts emitting it.
  - `upsert_entries` in `dry_run=True` mode makes ZERO calls to the embedder
    or Chroma (the cost-saver the operator relies on).
  - Backfill respects all three knobs end-to-end.
  - The watcher respects all three knobs end-to-end.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from log_dashboard.config import Settings
from log_dashboard.ingest.backfill import run_initial_backfill
from log_dashboard.ingest.embeddings import filter_for_ingest
from log_dashboard.ingest.parsers import (
    parse_logback_line,
    parse_structlog_line,
    parse_winston_line,
)
from log_dashboard.ingest.spec import APP_LOGS
from log_dashboard.ingest.vectorstore import upsert_entries
from log_dashboard.ingest.watcher import _AppLogHandler
from log_dashboard.schemas import LogEntry, LogLevel

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


def _entry(
    seq: int,
    *,
    app: str = "fnol",
    level: LogLevel = LogLevel.INFO,
    source: str = "prod",
    event: str = "claim_submitted",
) -> LogEntry:
    return LogEntry(
        id=f"{app}:{seq}",
        timestamp=datetime(2026, 6, 4, 12, 0, seq, tzinfo=UTC),
        level=level,
        app=app,
        event=event,
        fields={},
        raw=f'{{"event":"{event}","seq":{seq}}}',
        source=source,
    )


def _structlog_line(*, event: str, level: str = "info", **fields: object) -> str:
    payload = {
        "event": event,
        "level": level,
        "timestamp": datetime(2026, 6, 4, 12, 0, 0, tzinfo=UTC).isoformat(),
        **fields,
    }
    return json.dumps(payload)


def _winston_line(*, event: str, level: str = "info", **fields: object) -> str:
    payload = {
        "level": level,
        "message": event,
        "event": event,
        "timestamp": datetime(2026, 6, 4, 12, 0, 0, tzinfo=UTC).isoformat(),
        "service": "customer-portal",
        **fields,
    }
    return json.dumps(payload)


def _logback_line(*, event: str = "request", level: str = "INFO", path: str = "/api/x") -> str:
    return (
        "2026-06-04 12:00:00.000 "
        f"{level}  --- [http-nio-8080-exec-1] "
        "com.example.RequestLoggingFilter : "
        f"{event} method=GET path={path} status=200"
    )


def _settings(volume_root: Path, **overrides: object) -> Settings:
    base = dict(
        jwt_secret="test-secret",
        admin_username="admin",
        admin_password="hunter2",
        openai_api_key="sk-test",
        log_volume_root=volume_root,
        embedding_batch_size=50,
    )
    base.update(overrides)
    return Settings(**base)


# ---------------------------------------------------------------------------
# 1. filter_for_ingest helper
# ---------------------------------------------------------------------------


def test_filter_keeps_only_intersection_of_levels_and_sources() -> None:
    entries = [
        _entry(0, level=LogLevel.INFO, source="prod"),
        _entry(1, level=LogLevel.WARN, source="prod"),
        _entry(2, level=LogLevel.ERROR, source="prod"),
        _entry(3, level=LogLevel.WARN, source="health"),
        _entry(4, level=LogLevel.ERROR, source="test"),
    ]
    kept = filter_for_ingest(
        entries,
        levels=frozenset({LogLevel.WARN, LogLevel.ERROR}),
        sources=frozenset({"prod"}),
    )
    assert [e.id for e in kept] == ["fnol:1", "fnol:2"]


def test_filter_empty_input_is_safe() -> None:
    assert (
        filter_for_ingest(
            [],
            levels=frozenset({LogLevel.WARN}),
            sources=frozenset({"prod"}),
        )
        == []
    )


def test_filter_respects_a_custom_level_set() -> None:
    entries = [
        _entry(0, level=LogLevel.DEBUG, source="prod"),
        _entry(1, level=LogLevel.INFO, source="prod"),
    ]
    kept = filter_for_ingest(
        entries,
        levels=frozenset({LogLevel.DEBUG, LogLevel.INFO}),
        sources=frozenset({"prod"}),
    )
    assert len(kept) == 2


# ---------------------------------------------------------------------------
# 2. parser source-tagging
# ---------------------------------------------------------------------------


def test_structlog_health_request_is_tagged_source_health() -> None:
    line = _structlog_line(event="request", path="/health", status=200)
    entry = parse_structlog_line(app="shared-data-api", seq=0, line=line)
    assert entry is not None
    assert entry.source == "health"
    assert "source" not in entry.fields  # tag lives on LogEntry, not in fields


def test_structlog_request_missing_source_field_is_tagged_unknown() -> None:
    """A request line without an explicit `source` field is tagged `unknown`
    after the Phase 7e source-propagation slice — the X-Source chain now
    ships end-to-end across all 4 apps, so missing source is a code smell,
    not a happy-path default. Operator-visible in the UI; admitted through
    the gate by default so leaks stay observable."""
    line = _structlog_line(event="request", path="/policies/me", status=200)
    entry = parse_structlog_line(app="shared-data-api", seq=0, line=line)
    assert entry is not None
    assert entry.source == "unknown"


def test_structlog_request_with_explicit_source_prod_is_tagged_prod() -> None:
    """A request line WITH `source=prod` from the middleware (the normal
    real-user case) is tagged `prod`."""
    line = _structlog_line(event="request", path="/policies/me", status=200, source="prod")
    entry = parse_structlog_line(app="shared-data-api", seq=0, line=line)
    assert entry is not None
    assert entry.source == "prod"


def test_structlog_explicit_source_field_wins_over_path_inference() -> None:
    # When a non-request event carries an explicit `source` field (per
    # ADR-011's X-Source convention or an app's business-logic logger), the
    # parser MUST honour it instead of defaulting to "prod".
    line = _structlog_line(event="claim_submitted", source="test")
    entry = parse_structlog_line(app="fnol", seq=0, line=line)
    assert entry is not None
    assert entry.source == "test"


def test_health_path_request_overrides_explicit_source() -> None:
    # ADR-011: each app's request-logger middleware emits `source=prod` by
    # default. The parser MUST still tag healthcheck requests as `health` so
    # heartbeat doesn't leak into Chroma — path is an immutable property the
    # header cannot override.
    line = _structlog_line(event="request", path="/health", status=200, source="prod")
    entry = parse_structlog_line(app="shared-data-api", seq=0, line=line)
    assert entry is not None
    assert entry.source == "health"


def test_winston_health_request_is_tagged_source_health() -> None:
    line = _winston_line(event="request", path="/health", status=200)
    entry = parse_winston_line(app="customer-portal", seq=0, line=line)
    assert entry is not None
    assert entry.source == "health"


def test_logback_actuator_health_is_tagged_source_health() -> None:
    line = _logback_line(event="request", level="INFO", path="/actuator/health")
    entry = parse_logback_line(app="agent-portal", seq=0, line=line)
    assert entry is not None
    assert entry.source == "health"


def test_logback_explicit_source_in_kv_wins() -> None:
    line = (
        "2026-06-04 12:00:00.000 INFO  --- [main] com.example.Test : "
        "claims_fetched source=test count=5"
    )
    entry = parse_logback_line(app="agent-portal", seq=0, line=line)
    assert entry is not None
    assert entry.source == "test"
    # `source` lives on the LogEntry, never duplicated in fields.
    assert "source" not in entry.fields


# ---------------------------------------------------------------------------
# 3. dry-run mode — the no-OpenAI-spend guarantee
# ---------------------------------------------------------------------------


def test_dry_run_makes_zero_embedder_calls() -> None:
    """The cost-saver the operator relies on: with DASHBOARD_INGEST_DRY_RUN
    set, the embedder is never invoked even for entries that pass the filter.
    """
    import uuid

    import chromadb
    from langchain_chroma import Chroma

    class CountingEmbeddings:
        def __init__(self) -> None:
            self.embed_documents_calls = 0

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.embed_documents_calls += 1
            return [[0.0] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            return [0.0]

    embedder = CountingEmbeddings()
    store = Chroma(
        client=chromadb.Client(),
        collection_name=f"dry-run-{uuid.uuid4().hex[:8]}",
        embedding_function=embedder,
    )
    entries = [_entry(i, level=LogLevel.ERROR, source="prod") for i in range(5)]

    # Dry-run path — returns 0, no calls.
    embedded = upsert_entries(store, entries, dry_run=True)
    assert embedded == 0
    assert embedder.embed_documents_calls == 0
    assert store._collection.count() == 0

    # Live path — embeds and counts up.
    embedded = upsert_entries(store, entries, dry_run=False)
    assert embedded == 5
    assert embedder.embed_documents_calls == 1


# ---------------------------------------------------------------------------
# 4. backfill end-to-end with default filter
# ---------------------------------------------------------------------------


def test_backfill_with_default_filter_drops_info_and_health(log_volume, fake_vectorstore) -> None:
    # 1 INFO request (not health) + 1 INFO health request +
    # 1 WARN business event + 1 ERROR. Default filter keeps only the last two.
    log_volume["fnol"].write_text(
        "\n".join(
            [
                _structlog_line(event="request", path="/api/x", status=200),
                _structlog_line(event="request", path="/health", status=200),
                _structlog_line(event="sda_upstream_rejected", level="warning"),
                _structlog_line(event="unhandled_exception", level="error"),
            ]
        )
        + "\n"
    )
    settings = _settings(log_volume["fnol"].parent.parent)  # defaults — WARN+ERROR, prod
    results = run_initial_backfill(settings, fake_vectorstore)
    fnol = next(r for r in results if r.app == "fnol")

    assert fnol.active_lines == 4
    assert fnol.passed_filter == 2  # WARN + ERROR
    assert fnol.embedded == 2
    assert fake_vectorstore._collection.count() == 2


def test_backfill_dry_run_passes_filter_but_skips_chroma(log_volume, fake_vectorstore) -> None:
    log_volume["fnol"].write_text(
        _structlog_line(event="unhandled_exception", level="error") + "\n"
    )
    settings = _settings(
        log_volume["fnol"].parent.parent,
        dashboard_ingest_dry_run=True,
    )
    results = run_initial_backfill(settings, fake_vectorstore)
    fnol = next(r for r in results if r.app == "fnol")

    assert fnol.passed_filter == 1  # filter saw the ERROR
    assert fnol.embedded == 0  # dry-run short-circuited the upsert
    assert fake_vectorstore._collection.count() == 0


# ---------------------------------------------------------------------------
# 5. watcher end-to-end with default filter
# ---------------------------------------------------------------------------


def test_watcher_with_default_filter_drops_info_and_health(log_volume, fake_vectorstore) -> None:
    fnol_applog = next(al for al in APP_LOGS if al.name == "fnol")
    path = log_volume["fnol"]
    settings = _settings(log_volume["fnol"].parent.parent)  # default filter
    handler = _AppLogHandler(fnol_applog, path, fake_vectorstore, settings, initial_offset=0)

    path.write_text(
        "\n".join(
            [
                _structlog_line(event="request", path="/api/x", status=200),  # INFO prod
                _structlog_line(event="request", path="/health", status=200),  # INFO health
                _structlog_line(event="sda_upstream_unreachable", level="error"),  # ERROR prod
            ]
        )
        + "\n"
    )

    ev = MagicMock()
    ev.is_directory = False
    ev.src_path = str(path)
    handler.on_modified(ev)

    # Only the ERROR prod entry should land in Chroma.
    assert fake_vectorstore._collection.count() == 1
