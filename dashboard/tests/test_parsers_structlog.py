from log_dashboard.ingest.embeddings import make_doc_id
from log_dashboard.ingest.parsers import parse_structlog_line
from log_dashboard.schemas import LogLevel


def test_parses_sda_request_line() -> None:
    line = (
        '{"caller": "agent-portal", "user": "6a20927088194556bda4881e", '
        '"method": "GET", "path": "/claims/487e", "status": 200, '
        '"duration_ms": 3.29, "event": "request", "logger": "request", '
        '"level": "info", "timestamp": "2026-06-04T16:31:02.133269Z"}'
    )
    entry = parse_structlog_line(app="shared-data-api", seq=0, line=line)
    assert entry is not None
    # `id` is content-hash-derived (PR 4b) so /errors/{id} URLs are stable
    # across requests and match the Chroma document ID.
    assert entry.id == make_doc_id("shared-data-api", line)
    assert entry.id.startswith("shared-data-api:")
    assert len(entry.id.split(":", 1)[1]) == 16
    assert entry.app == "shared-data-api"
    assert entry.event == "request"
    assert entry.level is LogLevel.INFO
    assert entry.timestamp.isoformat() == "2026-06-04T16:31:02.133269+00:00"
    assert entry.fields["caller"] == "agent-portal"
    assert entry.fields["status"] == 200
    assert entry.fields["duration_ms"] == 3.29
    assert "level" not in entry.fields
    assert entry.raw == line


def test_parses_business_event_with_only_required_fields() -> None:
    line = (
        '{"event": "startup_complete", "level": "info", '
        '"timestamp": "2026-06-04T16:30:00.000000Z"}'
    )
    entry = parse_structlog_line(app="fnol", seq=7, line=line)
    assert entry is not None
    assert entry.event == "startup_complete"
    assert entry.level is LogLevel.INFO
    assert entry.fields == {}


def test_normalizes_warning_to_warn_and_uppercase_levels() -> None:
    line = (
        '{"event": "login_failed", "level": "warning", '
        '"username": "alice", "reason": "bad_password", '
        '"timestamp": "2026-06-04T16:30:00.000000Z"}'
    )
    entry = parse_structlog_line(app="shared-data-api", seq=0, line=line)
    assert entry is not None
    assert entry.level is LogLevel.WARN


def test_returns_none_for_malformed_json() -> None:
    assert parse_structlog_line(app="fnol", seq=0, line="not-json{") is None
    assert parse_structlog_line(app="fnol", seq=0, line="") is None
    # Missing required fields
    assert parse_structlog_line(app="fnol", seq=0, line='{"event": "x", "level": "info"}') is None
    # JSON array, not dict
    assert parse_structlog_line(app="fnol", seq=0, line="[1,2,3]") is None
