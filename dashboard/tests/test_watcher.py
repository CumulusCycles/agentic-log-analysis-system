"""Tests for the watchdog-driven incremental ingestion module."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from log_dashboard.config import Settings
from log_dashboard.ingest.spec import APP_LOGS
from log_dashboard.ingest.watcher import LogVolumeWatcher, _AppLogHandler


def _structlog_line(event: str, **fields) -> str:
    payload = {
        "event": event,
        "level": "info",
        "timestamp": datetime(2026, 6, 4, 12, 0, 0, tzinfo=UTC).isoformat(),
        **fields,
    }
    return json.dumps(payload)


def _settings(volume_root: Path) -> Settings:
    # These mechanics tests assert on watcher plumbing (offset, dedup,
    # lifecycle). Open the gate to all levels + sources so filter behavior
    # doesn't interfere; filter behavior is covered by test_ingest_filter.py.
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


def _fnol_applog():
    return next(al for al in APP_LOGS if al.name == "fnol")


def _modify_event(path: Path) -> MagicMock:
    """Synthesize a watchdog modify event for `path`."""
    ev = MagicMock()
    ev.is_directory = False
    ev.src_path = str(path)
    return ev


def test_watcher_appends_new_lines_to_the_store(log_volume, fake_vectorstore) -> None:
    fnol = _fnol_applog()
    path = log_volume["fnol"]
    settings = _settings(log_volume["fnol"].parent.parent)
    # Pre-existing content already in Chroma (simulated): backfill has set the
    # initial offset = current file size.
    path.write_text(_structlog_line("startup_complete") + "\n")
    initial_size = path.stat().st_size

    handler = _AppLogHandler(fnol, path, fake_vectorstore, settings, initial_offset=initial_size)
    # New line appended after the watcher started.
    with path.open("a") as f:
        f.write(_structlog_line("claim_submitted", claim_id="C-99") + "\n")

    handler.on_modified(_modify_event(path))

    # Exactly one new doc — startup_complete was excluded by initial_offset.
    assert fake_vectorstore._collection.count() == 1
    # Offset advanced to current EOF.
    assert handler.offset == path.stat().st_size


def test_watcher_ignores_directory_events_and_other_paths(log_volume, fake_vectorstore) -> None:
    fnol = _fnol_applog()
    path = log_volume["fnol"]
    settings = _settings(log_volume["fnol"].parent.parent)
    handler = _AppLogHandler(fnol, path, fake_vectorstore, settings, initial_offset=0)

    # Append data so on_modified would have something to read.
    path.write_text(_structlog_line("claim_submitted") + "\n")

    # Directory event — must be ignored.
    dir_event = MagicMock()
    dir_event.is_directory = True
    dir_event.src_path = str(path)
    handler.on_modified(dir_event)
    assert fake_vectorstore._collection.count() == 0

    # Different file in the same dir — must be ignored.
    other = path.parent / "other.log"
    other.write_text("noise\n")
    other_event = _modify_event(other)
    handler.on_modified(other_event)
    assert fake_vectorstore._collection.count() == 0


def test_watcher_dedupes_when_offset_overlaps_already_indexed_content(
    log_volume, fake_vectorstore
) -> None:
    """When the watcher's offset is BEHIND the actual EOF (e.g., backfill
    finished and the watcher started with a slightly-stale offset), the
    re-read overlaps with content that's already in Chroma. Content-hash
    IDs make the upsert a no-op rather than creating duplicates.
    """
    fnol = _fnol_applog()
    path = log_volume["fnol"]
    settings = _settings(log_volume["fnol"].parent.parent)
    line = _structlog_line("claim_submitted") + "\n"
    path.write_text(line + line + line)  # 3 identical-content lines

    # Offset starts at 0 — first read pulls all 3 lines.
    handler = _AppLogHandler(fnol, path, fake_vectorstore, settings, initial_offset=0)
    handler.on_modified(_modify_event(path))
    first_count = fake_vectorstore._collection.count()

    # Simulate a stale offset by rewinding and replaying.
    handler.offset = 0
    handler.on_modified(_modify_event(path))
    # Same content → same IDs → upsert is idempotent.
    assert fake_vectorstore._collection.count() == first_count


def test_watcher_constructor_uses_supplied_initial_offsets(log_volume, fake_vectorstore) -> None:
    """When the lifespan passes per-app initial offsets, they should be
    applied to the handler so backfill→watcher handoff is seamless.
    """
    log_volume["fnol"].write_text(_structlog_line("a") + "\n")
    settings = _settings(log_volume["fnol"].parent.parent)
    watcher = LogVolumeWatcher(
        settings,
        fake_vectorstore,
        initial_offsets={"fnol": 12345, "shared-data-api": 99},
        observer=MagicMock(),
    )
    by_app = {h.app_log.name: h for h in watcher._handlers}
    assert by_app["fnol"].offset == 12345
    assert by_app["shared-data-api"].offset == 99
    # Apps not in the offsets dict fall back to current EOF.
    assert by_app["customer-portal"].offset == 0
