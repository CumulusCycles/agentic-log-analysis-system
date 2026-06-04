from log_dashboard.ingest.parsers import parse_logback_line
from log_dashboard.schemas import LogLevel


def test_parses_request_line_with_key_value_tail() -> None:
    line = (
        "2026-06-04 16:30:59.220 INFO  --- [http-nio-8080-exec-10] "
        "com.cumuluscycles.agentportal.logging.RequestLoggingFilter : "
        "request method=GET path=/api/claims caller=- user=6a20927 "
        "status=200 duration_ms=6.06"
    )
    entry = parse_logback_line(app="agent-portal", seq=0, line=line)
    assert entry is not None
    assert entry.level is LogLevel.INFO
    assert entry.event == "request"
    assert entry.timestamp.isoformat() == "2026-06-04T16:30:59.220000+00:00"
    assert entry.fields["thread"] == "http-nio-8080-exec-10"
    assert entry.fields["method"] == "GET"
    assert entry.fields["path"] == "/api/claims"
    assert entry.fields["status"] == "200"
    assert entry.fields["caller"] == "-"


def test_handles_padded_level_with_two_spaces() -> None:
    # Logback right-pads 4-char levels (INFO, WARN) so the gap before "---" is
    # 2 spaces, not 1. The parser must accept either width.
    line = (
        "2026-06-04 16:30:59.972 WARN  --- [http-nio-8080-exec-7] "
        "com.cumuluscycles.agentportal.sda.SdaClient : "
        "sda_upstream_rejected target=/auth/login status=401 "
        "detail=invalid credentials"
    )
    entry = parse_logback_line(app="agent-portal", seq=0, line=line)
    assert entry is not None
    assert entry.level is LogLevel.WARN
    assert entry.event == "sda_upstream_rejected"
    # `detail` carries spaces — the kv parser must capture the trailing words.
    assert entry.fields["detail"] == "invalid credentials"
    assert entry.fields["target"] == "/auth/login"


def test_returns_none_for_continuation_line() -> None:
    # Stack-trace continuation lines start with whitespace + class name + colon.
    # The reader will fold these; the parser itself just returns None.
    assert (
        parse_logback_line(app="agent-portal", seq=0, line="\tat com.foo.Bar.baz(Bar.java:42)")
        is None
    )
    assert (
        parse_logback_line(app="agent-portal", seq=0, line="Caused by: java.lang.RuntimeException")
        is None
    )


def test_returns_none_for_empty_or_short_line() -> None:
    assert parse_logback_line(app="agent-portal", seq=0, line="") is None
    assert parse_logback_line(app="agent-portal", seq=0, line="garbage") is None


def test_event_falls_back_to_logger_basename_when_message_has_no_tokens() -> None:
    line = (
        "2026-06-04 16:30:00.000 INFO  --- [main] "
        "com.cumuluscycles.agentportal.AgentPortalApplication : "
        "Started AgentPortalApplication in 3.21 seconds"
    )
    entry = parse_logback_line(app="agent-portal", seq=0, line=line)
    assert entry is not None
    # The first token is "Started"; the kv parser finds nothing.
    assert entry.event == "Started"
    assert entry.level is LogLevel.INFO
