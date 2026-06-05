"""Unit tests for `credentials.sanitize_user_input` + `sanitize_log_raw`.

Each parameterised case asserts that a known-credential-shaped substring is
redacted to `[REDACTED]` while the surrounding text survives, OR that a
clean string passes through unchanged.

The two sanitisers share the same redaction pool — sanity-check at the
bottom that both honour the same shapes.
"""

from __future__ import annotations

import pytest

from log_dashboard.credentials import sanitize_log_raw, sanitize_user_input


@pytest.mark.parametrize(
    "raw,expected_in,expected_not_in",
    [
        # Bearer in header form
        (
            "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9zzzzzzzzzzz",
            "[REDACTED]",
            "eyJhbGciOiJIUzI1NiJ9zzzzzzzzzzz",
        ),
        # Bare Bearer (note: token must be ≥20 chars to match)
        (
            "use Bearer ghp_abcdefghijklmnopqrst when calling",
            "[REDACTED]",
            "ghp_abcdefghijklmnopqrst",
        ),
        # X-API-Key header
        (
            "curl -H 'X-API-Key: fnol_app_api_key_change_me' /policies",
            "[REDACTED]",
            "fnol_app_api_key_change_me",
        ),
        # password= form
        ("login with password=hunter2 OK", "[REDACTED]", "hunter2"),
        # password: form
        ("yaml: password: hunter2", "[REDACTED]", "hunter2"),
        # JSON "password": "..." form
        ('payload {"password": "hunter2", "user": "alice"}', "[REDACTED]", "hunter2"),
        # JWT-shaped token (three base64url segments)
        (
            "got JWT eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.abcdefghijklmnopqrstuvwxyz",
            "[REDACTED]",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.abcdefghijklmnopqrstuvwxyz",
        ),
        # DSN: postgres
        (
            "connect postgresql://postgres:secretpw@postgres:5432/insurance",
            "[REDACTED]",
            "secretpw",
        ),
        # DSN: mongodb+srv
        (
            "uri mongodb+srv://admin:p4ssw0rd@cluster0.mongodb.net/db",
            "[REDACTED]",
            "p4ssw0rd",
        ),
        # DSN: mysql
        (
            "MYSQL_URL=mysql://root:r00tpw@127.0.0.1:3306/insurance",
            "[REDACTED]",
            "r00tpw",
        ),
        # DSN: redis
        ("redis://default:r3d1spw@redis:6379", "[REDACTED]", "r3d1spw"),
    ],
)
def test_sanitize_user_input_redacts(raw: str, expected_in: str, expected_not_in: str) -> None:
    out = sanitize_user_input(raw)
    assert expected_in in out
    assert expected_not_in not in out


@pytest.mark.parametrize(
    "raw",
    [
        "what is wrong with fnol?",
        "I see a 500 error from the customer-portal — when did it start?",
        "tell me the status of agent-portal",
        "list the most recent ERROR events",
        "",  # empty input
    ],
)
def test_sanitize_user_input_clean_passes_through(raw: str) -> None:
    assert sanitize_user_input(raw) == raw


def test_sanitize_user_input_truncates_huge_blobs() -> None:
    """An 8000-char blob is kept; 9000 chars get truncated + an ellipsis."""
    blob = "A" * 9000
    out = sanitize_user_input(blob)
    assert out.endswith("…")
    # 8000 chars + the single-character ellipsis
    assert len(out) == 8001


def test_sanitize_log_raw_redacts_dsn_in_log_line() -> None:
    """Belt-and-braces: a log line that accidentally echoes a DSN never
    reaches the LLM context with the password visible."""
    raw = '{"event":"db_connected","uri":"postgres://postgres:secretpw@postgres:5432/insurance"}'
    out = sanitize_log_raw(raw)
    assert "[REDACTED]" in out
    assert "secretpw" not in out


def test_sanitize_log_raw_jwt_in_request_log() -> None:
    raw = (
        "INFO request_complete caller=fnol user=alice token="
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbGljZSJ9.signature_segment_at_least_20_chars"
    )
    out = sanitize_log_raw(raw)
    assert "[REDACTED]" in out
    assert "signature_segment_at_least_20_chars" not in out


def test_sanitize_log_raw_empty_returns_empty() -> None:
    assert sanitize_log_raw("") == ""


def test_both_sanitisers_share_redaction_pool() -> None:
    """Same input → both sanitisers redact the same span. Regression guard
    against future drift between the two."""
    raw = "header Authorization: Bearer eyJabcdefghijklmnopqrstuvwxyz"
    assert sanitize_user_input(raw) == sanitize_log_raw(raw)
