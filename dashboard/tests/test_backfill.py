"""Tests for the Phase 7d initial-backfill module."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from log_dashboard.config import Settings
from log_dashboard.ingest.backfill import run_initial_backfill


def _structlog_line(event: str, level: str = "info", **fields) -> str:
    payload = {
        "event": event,
        "level": level,
        "timestamp": datetime(2026, 6, 4, 12, 0, 0, tzinfo=UTC).isoformat(),
        **fields,
    }
    return json.dumps(payload)


def _winston_line(event: str, level: str = "info", **fields) -> str:
    payload = {
        "level": level,
        "message": event,
        "timestamp": datetime(2026, 6, 4, 12, 0, 0, tzinfo=UTC).isoformat(),
        "service": "customer-portal",
        **fields,
    }
    return json.dumps(payload)


def _logback_line(event: str = "request", level: str = "INFO") -> str:
    return (
        "2026-06-04 12:00:00.000 "
        f"{level}  --- [http-nio-8080-exec-1] "
        "com.example.RequestLoggingFilter : "
        f"{event} method=GET path=/api/x status=200"
    )


def _settings(volume_root: Path) -> Settings:
    # These mechanics tests assert on the backfill plumbing (parse, dedup,
    # gz archives, watcher offset handoff), not on the ingest filter.
    # Open the gate to all levels + sources so filter behavior doesn't
    # interfere; filter behavior is covered by test_ingest_filter.py.
    from log_dashboard.schemas import LogLevel

    return Settings(
        jwt_secret="test-secret",
        admin_username="admin",
        admin_password="hunter2",
        log_volume_root=volume_root,
        embedding_batch_size=50,
        dashboard_ingest_levels=frozenset(LogLevel),
        dashboard_ingest_sources=frozenset({"prod", "health", "test", "unknown"}),
    )


def test_backfill_reads_all_four_apps(log_volume, fake_vectorstore) -> None:
    log_volume["shared-data-api"].write_text(_structlog_line("startup_complete") + "\n")
    log_volume["fnol"].write_text(_structlog_line("claim_submitted") + "\n")
    log_volume["customer-portal"].write_text(_winston_line("login_success") + "\n")
    log_volume["agent-portal"].write_text(_logback_line() + "\n")

    settings = _settings(log_volume["fnol"].parent.parent)
    results = run_initial_backfill(settings, fake_vectorstore)

    by_app = {r.app: r for r in results}
    assert by_app["shared-data-api"].embedded == 1
    assert by_app["fnol"].embedded == 1
    assert by_app["customer-portal"].embedded == 1
    assert by_app["agent-portal"].embedded == 1
    # Total in Chroma matches the 4 lines we wrote.
    assert fake_vectorstore._collection.count() == 4


def test_backfill_is_idempotent_across_restarts(log_volume, fake_vectorstore) -> None:
    log_volume["fnol"].write_text(
        _structlog_line("claim_submitted", claim_id="C-1")
        + "\n"
        + _structlog_line("claim_submitted", claim_id="C-2")
        + "\n"
    )
    settings = _settings(log_volume["fnol"].parent.parent)

    run_initial_backfill(settings, fake_vectorstore)
    first_count = fake_vectorstore._collection.count()
    run_initial_backfill(settings, fake_vectorstore)
    run_initial_backfill(settings, fake_vectorstore)
    # Content-stable IDs make re-runs no-ops at the Chroma layer.
    assert fake_vectorstore._collection.count() == first_count == 2


def test_backfill_reads_rotated_gz_archives(log_volume, fake_vectorstore) -> None:
    # Active file: 1 line. Archive: 2 lines. Total expected: 3.
    active = log_volume["agent-portal"]
    active.write_text(_logback_line("request") + "\n")

    archive_path = active.parent / "agent-portal.log.2026-06-03.0.gz"
    archive_content = (
        _logback_line("login_proxied_success") + "\n" + _logback_line("claims_fetched") + "\n"
    )
    with gzip.open(archive_path, "wt", encoding="utf-8") as f:
        f.write(archive_content)

    settings = _settings(log_volume["agent-portal"].parent.parent)
    results = run_initial_backfill(settings, fake_vectorstore)
    ap_result = next(r for r in results if r.app == "agent-portal")

    assert ap_result.archive_lines == 2
    assert ap_result.active_lines == 1
    assert ap_result.embedded == 3


def test_backfill_returns_active_size_bytes_for_watcher_handoff(
    log_volume, fake_vectorstore
) -> None:
    content = _structlog_line("startup_complete") + "\n"
    log_volume["fnol"].write_text(content)
    expected_size = log_volume["fnol"].stat().st_size

    settings = _settings(log_volume["fnol"].parent.parent)
    results = run_initial_backfill(settings, fake_vectorstore)
    fnol_result = next(r for r in results if r.app == "fnol")

    # active_size_bytes is the contract the watcher uses to set its initial
    # byte-offset so the two stages don't double-process the same content.
    assert fnol_result.active_size_bytes == expected_size


def test_backfill_handles_missing_log_files(tmp_path, fake_vectorstore) -> None:
    # Volume root exists but the per-app log files don't (a never-run app).
    # Backfill should NOT crash — the dashboard must stay usable.
    settings = _settings(tmp_path)
    results = run_initial_backfill(settings, fake_vectorstore)
    assert len(results) == 4
    for r in results:
        assert r.active_lines == 0
        assert r.embedded == 0


@pytest.fixture
def _unused():
    """Placeholder to silence pytest discovery on this file when run alone."""
    yield
