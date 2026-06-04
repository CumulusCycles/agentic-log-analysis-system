"""Initial backfill: on lifespan startup, scan each app's active `.log` file
PLUS any rotated `.gz` archives in the same directory, parse via 7b's
`parse_line` + `parse_and_fold`, and upsert into Chroma in batches.

Idempotent — content-stable doc IDs mean a restart safely re-runs without
creating duplicates.
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from log_dashboard.config import Settings
from log_dashboard.ingest.embeddings import filter_for_ingest
from log_dashboard.ingest.reader import parse_and_fold
from log_dashboard.ingest.spec import APP_LOGS
from log_dashboard.ingest.vectorstore import upsert_entries
from log_dashboard.logging_setup import get_logger

if TYPE_CHECKING:
    from langchain_chroma import Chroma

log = get_logger("ingest.backfill")


@dataclass(frozen=True)
class BackfillResult:
    """Per-app summary, joined into a single startup log line.

    `active_size_bytes` is the size of the active log file at the moment
    backfill read it — used by the watcher to set its initial byte-offset
    so incremental ingestion resumes from exactly where backfill stopped.
    Content-hash IDs make any small overlap idempotent.

    `passed_filter` is the count of entries that made it through the
    ingest-level + ingest-source gate. `embedded` is the count actually
    sent to OpenAI (after dedup + dry-run). Operator can read these two
    numbers to see what the filter is doing without paying anything.
    """

    app: str
    active_lines: int
    active_size_bytes: int
    archive_lines: int
    passed_filter: int
    embedded: int


def run_initial_backfill(settings: Settings, store: Chroma) -> list[BackfillResult]:
    """Scan all 4 app log volumes (active + rotated archives) and upsert into
    `store`. Returns per-app counts so the caller can log a summary.

    Idempotency: content-hash IDs mean re-running this on every restart is
    safe and cheap (Chroma upsert deduplicates).
    """
    results: list[BackfillResult] = []
    for app_log in APP_LOGS:
        active_path = app_log.absolute_path(settings.log_volume_root)
        active_lines, active_size = _read_text_lines_with_size(active_path)
        archive_lines: list[str] = []
        for gz_path in _find_rotated_archives(active_path):
            archive_lines.extend(_read_gzip_lines(gz_path))
        # Archives are rotated copies of older log content — embed them in
        # chronological order (archives oldest, then active).
        all_lines = archive_lines + active_lines
        parsed = parse_and_fold(app_log, all_lines)
        # Apply the ingest gate BEFORE upsert. Skipped entries never reach
        # OpenAI and never land in Chroma.
        passing = filter_for_ingest(
            parsed,
            levels=settings.dashboard_ingest_levels,
            sources=settings.dashboard_ingest_sources,
        )
        embedded = upsert_entries(
            store,
            passing,
            batch_size=settings.embedding_batch_size,
            dry_run=settings.dashboard_ingest_dry_run,
        )
        results.append(
            BackfillResult(
                app=app_log.name,
                active_lines=len(active_lines),
                active_size_bytes=active_size,
                archive_lines=len(archive_lines),
                passed_filter=len(passing),
                embedded=embedded,
            )
        )
        log.info(
            "backfill_app_complete",
            app=app_log.name,
            active_lines=len(active_lines),
            archive_lines=len(archive_lines),
            parsed=len(parsed),
            passed_filter=len(passing),
            embedded=embedded,
            dry_run=settings.dashboard_ingest_dry_run,
        )
    return results


def _read_text_lines_with_size(path: Path) -> tuple[list[str], int]:
    """Read every line of `path` plus the file size we read up to.

    The byte-size return value is the contract for resuming incremental
    ingestion: the watcher uses it as its initial offset so it doesn't
    re-process content the backfill already embedded. Content-hash IDs make
    a small overlap idempotent, so off-by-a-few bytes is harmless.

    Missing file → empty list + size 0; the dashboard must stay up even if
    one volume is missing (e.g., when an app has never run).
    """
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        log.info("backfill_file_missing", path=str(path))
        return [], 0
    except OSError as exc:
        log.warning("backfill_file_stat_failed", path=str(path), error_class=type(exc).__name__)
        return [], 0
    try:
        with path.open("rb") as f:
            data = f.read(size)
    except OSError as exc:
        log.warning("backfill_file_unreadable", path=str(path), error_class=type(exc).__name__)
        return [], 0
    text = data.decode("utf-8", errors="replace")
    return text.splitlines(), size


def _read_gzip_lines(path: Path) -> list[str]:
    """Read every line of a gzipped rotated archive."""
    try:
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()
    except OSError as exc:
        log.warning(
            "backfill_archive_unreadable",
            path=str(path),
            error_class=type(exc).__name__,
        )
        return []


def _find_rotated_archives(active_path: Path) -> list[Path]:
    """Find Logback-style rotated archives next to the active log.

    Logback emits `<stem>.YYYY-MM-DD.N.gz` (and Winston/structlog don't
    rotate within this project), so a simple glob covers all formats.
    Sorted oldest-first so backfill embeds archives in chronological order.
    """
    parent = active_path.parent
    if not parent.is_dir():
        return []
    stem = active_path.name  # e.g. "agent-portal.log"
    archives = sorted(parent.glob(f"{stem}.*.gz"))
    return archives
