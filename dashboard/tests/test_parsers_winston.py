from log_dashboard.ingest.parsers import parse_winston_line
from log_dashboard.schemas import LogLevel


def test_parses_cp_request_line() -> None:
    line = (
        '{"caller":"-","duration_ms":248.78,"event":"request","level":"info",'
        '"message":"request","method":"POST","path":"/auth/login",'
        '"service":"customer-portal","status":200,'
        '"timestamp":"2026-06-04T16:30:44.359Z","user":"-"}'
    )
    entry = parse_winston_line(app="customer-portal", seq=0, line=line)
    assert entry is not None
    assert entry.event == "request"
    assert entry.level is LogLevel.INFO
    assert entry.timestamp.isoformat() == "2026-06-04T16:30:44.359000+00:00"
    assert entry.fields["service"] == "customer-portal"
    assert entry.fields["status"] == 200
    # `message` and `event` are both removed from fields — they collapse to `entry.event`.
    assert "message" not in entry.fields
    assert "event" not in entry.fields


def test_falls_back_to_message_when_event_missing() -> None:
    # Some early winston configs only emit `message`. Make sure we still parse.
    line = (
        '{"level":"info","message":"server_started","timestamp":"2026-06-04T16:30:00.000Z",'
        '"service":"customer-portal"}'
    )
    entry = parse_winston_line(app="customer-portal", seq=0, line=line)
    assert entry is not None
    assert entry.event == "server_started"


def test_returns_none_for_malformed_json() -> None:
    assert parse_winston_line(app="customer-portal", seq=0, line="{bad") is None
    # Missing required fields
    assert parse_winston_line(app="customer-portal", seq=0, line='{"level":"info"}') is None
