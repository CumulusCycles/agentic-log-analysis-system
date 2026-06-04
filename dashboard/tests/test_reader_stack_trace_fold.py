from pathlib import Path

import structlog

from log_dashboard.ingest.reader import read_recent_entries
from log_dashboard.ingest.spec import AppLog, LogFormat


def test_continuation_lines_fold_into_previous_entry(tmp_path: Path) -> None:
    log_lines = [
        "2026-06-04 16:30:00.000 INFO  --- [main] com.foo : startup_complete",
        "2026-06-04 16:30:01.000 ERROR --- [http-1] com.foo : sda_call_failed",
        "java.lang.RuntimeException: oops",
        "\tat com.foo.Bar.baz(Bar.java:42)",
        "\tat com.foo.Bar.run(Bar.java:13)",
        "2026-06-04 16:30:02.000 INFO  --- [http-1] com.foo : request method=GET path=/x",
    ]
    f = tmp_path / "ap.log"
    f.write_text("\n".join(log_lines) + "\n")

    app_log = AppLog(name="agent-portal", relative_path="ap.log", fmt=LogFormat.LOGBACK_TEXT)
    entries = read_recent_entries(app_log, volume_root=tmp_path, limit=10)

    # Three real entries — the three continuation lines folded into entry[1].
    assert [e.event for e in entries] == ["startup_complete", "sda_call_failed", "request"]
    stack = entries[1].fields["stack_trace"]
    assert "java.lang.RuntimeException: oops" in stack
    assert "at com.foo.Bar.baz" in stack
    # raw includes the folded continuation lines too — so the Error Detail
    # screen can render the full trace verbatim.
    assert "java.lang.RuntimeException: oops" in entries[1].raw


def test_orphan_continuations_at_top_are_dropped_and_warned(tmp_path: Path) -> None:
    log_lines = [
        # First two lines are orphan continuations (no parent entry above).
        "\tat com.foo.Bar.baz(Bar.java:42)",
        "Caused by: java.lang.RuntimeException: orphan",
        "2026-06-04 16:30:01.000 INFO  --- [main] com.foo : real_event",
    ]
    f = tmp_path / "ap.log"
    f.write_text("\n".join(log_lines) + "\n")
    app_log = AppLog(name="agent-portal", relative_path="ap.log", fmt=LogFormat.LOGBACK_TEXT)

    with structlog.testing.capture_logs() as logs:
        entries = read_recent_entries(app_log, volume_root=tmp_path, limit=10)

    assert [e.event for e in entries] == ["real_event"]
    # Aggregate WARN with the count, not the orphan lines themselves.
    warnings = [e for e in logs if e.get("event") == "log_tail_orphan_continuations"]
    assert len(warnings) == 1
    assert warnings[0]["orphan_lines"] == 2
    assert warnings[0]["app"] == "agent-portal"
