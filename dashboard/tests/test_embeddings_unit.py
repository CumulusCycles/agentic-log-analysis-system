"""Pure-function tests for the embeddings helper module."""

from datetime import UTC, datetime

from log_dashboard.ingest.embeddings import (
    make_doc_id,
    make_metadata,
    make_page_content,
)
from log_dashboard.schemas import LogEntry, LogLevel


def _entry(**over) -> LogEntry:
    defaults = dict(
        id="fnol:0",
        timestamp=datetime(2026, 6, 4, 12, 0, 0, tzinfo=UTC),
        level=LogLevel.INFO,
        app="fnol",
        event="claim_submitted",
        fields={"claim_id": "C-100", "user": "alice"},
        raw='{"event":"claim_submitted","claim_id":"C-100","user":"alice"}',
    )
    defaults.update(over)
    return LogEntry(**defaults)


def test_make_doc_id_is_deterministic_for_the_same_raw_line() -> None:
    raw = '{"event":"x","ts":1}'
    assert make_doc_id("fnol", raw) == make_doc_id("fnol", raw)


def test_make_doc_id_differs_by_app_and_by_raw() -> None:
    assert make_doc_id("fnol", "a") != make_doc_id("fnol", "b")
    assert make_doc_id("fnol", "a") != make_doc_id("agent-portal", "a")
    # Stable shape: "{app}:{16 hex chars}".
    parts = make_doc_id("fnol", "a").split(":")
    assert parts[0] == "fnol"
    assert len(parts[1]) == 16
    assert all(c in "0123456789abcdef" for c in parts[1])


def test_make_page_content_includes_event_and_sorted_fields() -> None:
    text = make_page_content(_entry())
    # First line carries app + level + event.
    first_line = text.splitlines()[0]
    assert "[fnol]" in first_line
    assert "level=INFO" in first_line
    assert "event=claim_submitted" in first_line
    # Fields are rendered sorted by key.
    assert "claim_id=C-100" in text
    assert "user=alice" in text
    # Long field values are truncated at 200 chars + ellipsis.
    long_entry = _entry(fields={"big": "x" * 500})
    assert "…" in make_page_content(long_entry)


def test_make_metadata_includes_timestamp_epoch_and_stack_trace_flag() -> None:
    md = make_metadata(_entry())
    assert md["app"] == "fnol"
    assert md["level"] == "INFO"
    assert md["event"] == "claim_submitted"
    assert md["timestamp_epoch"] == datetime(2026, 6, 4, 12, 0, 0, tzinfo=UTC).timestamp()
    assert md["has_stack_trace"] is False
    # `raw` is duplicated into metadata so 7e's Error Detail can fetch the
    # full original line via a single Chroma query.
    assert md["raw"].startswith('{"event"')

    with_trace = _entry(fields={"stack_trace": "Traceback…"})
    assert make_metadata(with_trace)["has_stack_trace"] is True
