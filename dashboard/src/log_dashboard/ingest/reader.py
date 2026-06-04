"""Tail-style reader for the four log volumes.

Read the last N lines of a log file by seeking backward from EOF in fixed
chunks until we have ≥ N newlines. Partial first line (the one straddling
our seek boundary) is dropped — parsers return None on it and that's the
intended behaviour.

For the Agent Portal (Logback) format, multi-line stack traces have no
per-line timestamp. After parsing the tail, we walk the parsed entries and
fold continuation lines (lines whose parser returned None but that were
adjacent to a successfully parsed line) into the previous entry's
`fields["stack_trace"]`.
"""

from __future__ import annotations

from pathlib import Path

from ..logging_setup import get_logger
from ..schemas import LogEntry
from .parsers import parse_line
from .spec import AppLog, LogFormat

log = get_logger("ingest.reader")

# Read this many bytes per backward seek when chasing N lines from EOF.
# 16 KB is comfortably larger than any single line (including a folded stack
# trace) we expect, and small enough that we don't slurp megabytes for a
# 100-line tail.
_TAIL_CHUNK_BYTES = 16 * 1024


class LogReaderError(Exception):
    """Raised when a log file cannot be opened or read.

    Surfaced by the status endpoint as `status="error"` for the affected app.
    Caller MUST NOT include raw file contents in the message — only the
    exception class name and the absolute path.
    """


def tail_lines(path: Path, n: int) -> list[str]:
    """Return up to the last `n` newline-terminated lines of `path`.

    Lines come back in file order (oldest of the window first). Each
    returned line excludes the trailing newline. A truncated first line
    (because our backward seek window started mid-line) is dropped.

    Raises LogReaderError if the file is missing or unreadable.
    """
    if n <= 0:
        return []
    try:
        size = path.stat().st_size
    except FileNotFoundError as exc:
        raise LogReaderError(f"log file not found: {path}") from exc
    except OSError as exc:
        raise LogReaderError(f"log file unreadable: {path}") from exc
    if size == 0:
        return []

    try:
        with path.open("rb") as f:
            buf = bytearray()
            pos = size
            newlines = 0
            while pos > 0 and newlines <= n:
                step = min(_TAIL_CHUNK_BYTES, pos)
                pos -= step
                f.seek(pos)
                chunk = f.read(step)
                buf[:0] = chunk
                newlines = buf.count(b"\n")
            text = buf.decode("utf-8", errors="replace")
    except OSError as exc:
        raise LogReaderError(f"log file unreadable: {path}") from exc

    lines = text.splitlines()
    if pos > 0 and lines:
        # The first line is possibly truncated (we seeked into the middle of
        # it). Drop it — the parser would return None anyway, but explicit is
        # safer because a partial JSON line could occasionally parse.
        lines = lines[1:]
    if len(lines) > n:
        lines = lines[-n:]
    return lines


def _fold_logback_continuations(
    raw_lines: list[str], entries: list[LogEntry]
) -> tuple[list[LogEntry], int]:
    """Attach continuation lines to the previous entry as a stack trace.

    Walk `raw_lines` and `entries` in parallel — for every raw line that did
    NOT produce an entry, append it to the most recent entry's
    `fields["stack_trace"]` (and to its `raw`). Continuation lines that
    appear BEFORE any successfully parsed line are dropped (orphan tail).

    Returns (folded_entries, orphan_count). The orphan count is logged once
    at WARN by the caller so the operator knows the tail window may be too
    small for an in-flight stack trace.

    We do NOT log the orphan line content itself — that's a credential audit
    concern (the same as for malformed lines).
    """
    if not raw_lines:
        return entries, 0
    # Index entries by their raw line for O(1) "did this line produce an entry?".
    # We assume raw lines are unique-enough inside the tail window for this to
    # be safe; if a duplicate produced two entries, only the first folds and
    # that's still strictly correct (no invented data).
    parsed_by_raw: dict[str, LogEntry] = {e.raw: e for e in entries}
    folded: list[LogEntry] = []
    current: LogEntry | None = None
    orphans = 0
    for raw in raw_lines:
        entry = parsed_by_raw.get(raw)
        if entry is not None:
            current = entry
            folded.append(current)
            continue
        # Continuation candidate.
        if current is None:
            orphans += 1
            continue
        existing_trace = current.fields.get("stack_trace")
        if isinstance(existing_trace, str):
            new_trace = f"{existing_trace}\n{raw}"
        else:
            new_trace = raw
        # LogEntry is a pydantic model; mutate the dict + raw in place.
        current.fields["stack_trace"] = new_trace
        current.raw = f"{current.raw}\n{raw}"
    return folded, orphans


def parse_and_fold(app_log: AppLog, raw_lines: list[str]) -> list[LogEntry]:
    """Parse a list of raw log lines into entries, folding Logback multi-line
    stack traces into the previous entry. Returns entries in input order.

    Shared by `read_recent_entries` (tail-from-end path) and the Phase 7d
    `backfill` module (full-file scan path). For non-Logback formats the fold
    step is a no-op.
    """
    entries: list[LogEntry] = []
    for seq, raw in enumerate(raw_lines):
        entry = parse_line(fmt=app_log.fmt, app=app_log.name, seq=seq, line=raw)
        if entry is not None:
            entries.append(entry)
    if app_log.fmt is LogFormat.LOGBACK_TEXT:
        entries, orphans = _fold_logback_continuations(raw_lines, entries)
        if orphans:
            # One aggregate WARN per call, not per orphan, to keep volume sane.
            log.warning(
                "log_tail_orphan_continuations",
                app=app_log.name,
                orphan_lines=orphans,
            )
    return entries


def read_recent_entries(app_log: AppLog, *, volume_root: Path, limit: int) -> list[LogEntry]:
    """Read the last `limit` lines of `app_log` and parse them.

    For Logback (Agent Portal), multi-line stack traces are folded into the
    previous entry. For other formats, continuation handling is a no-op
    (their parsers handle one line each).

    Returns entries in file order (oldest first). The caller is responsible
    for sorting / filtering / paginating across multiple apps.

    Raises LogReaderError if the file is missing or unreadable.
    """
    path = app_log.absolute_path(volume_root)
    raw_lines = tail_lines(path, limit)
    return parse_and_fold(app_log, raw_lines)
