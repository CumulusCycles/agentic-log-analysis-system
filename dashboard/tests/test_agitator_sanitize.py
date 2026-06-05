"""Tests for `_sanitize_error` — the credential-discipline gate on `last_error`.

Defence-in-depth: scenarios don't raise with credentials today, but if a
future scenario does (or an httpx error message happens to wrap a header
value), the sanitizer must redact before storage. Two layers compose:
keyword match + JWT-shape match.
"""

from __future__ import annotations

import pytest

from log_dashboard.agitator.runs import _sanitize_error


@pytest.mark.parametrize(
    "needle",
    ["Authorization", "Bearer", "X-API-Key", "password"],
)
def test_sanitize_error_redacts_each_keyword(needle: str) -> None:
    """Any of the four credential-shaped keywords in a message → full redact."""
    message = f"upstream returned {needle}: something"
    assert _sanitize_error(message) == "redacted (contained sensitive header/field name)"


@pytest.mark.parametrize(
    "needle",
    ["authorization", "AUTHORIZATION", "Bearer", "x-api-key", "PASSWORD"],
)
def test_sanitize_error_keyword_match_is_case_insensitive(needle: str) -> None:
    message = f"error: {needle} missing"
    assert _sanitize_error(message) == "redacted (contained sensitive header/field name)"


def test_sanitize_error_redacts_jwt_shape_without_keyword() -> None:
    """A JWT-shaped token without any credential keyword nearby must still be
    redacted — that's the whole point of the shape check."""
    # 3 base64url-ish segments of >= 20 chars each, dot-separated.
    fake_jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiJ1c2VyIiwiaWF0IjoxNjA"
        ".abcdefghijklmnopqrstuvwxyz1234"
    )
    message = f"upstream sent {fake_jwt} back"
    assert _sanitize_error(message) == "redacted (contained JWT-shaped token)"


def test_sanitize_error_does_not_redact_normal_dotted_strings() -> None:
    """Dotted strings that are NOT JWT-shaped (e.g., URLs, version strings) pass through."""
    message = "request to http://shared-data-api:8000/policies failed at v1.2.3"
    assert _sanitize_error(message) == message


def test_sanitize_error_preserves_short_clean_message() -> None:
    assert _sanitize_error("upstream timeout") == "upstream timeout"


def test_sanitize_error_caps_long_message_with_ellipsis() -> None:
    long = "x" * 300
    result = _sanitize_error(long)
    assert len(result) == 201  # 200 chars + … (1 char)
    assert result.endswith("…")


def test_sanitize_error_keyword_match_beats_length_cap() -> None:
    """Keyword redaction takes precedence — even on a long message, we drop
    the whole thing rather than truncating to 200 chars that may still
    contain the credential."""
    long_with_creds = "Authorization Bearer " + ("x" * 300)
    assert _sanitize_error(long_with_creds) == "redacted (contained sensitive header/field name)"
