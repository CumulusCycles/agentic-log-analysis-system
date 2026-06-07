"""Unit tests for the shared credential-detection primitives.

These primitives are consumed by `credentials.py` (surgical-substitute
policy) and `agitator/runs.py::_sanitize_error` (drop-whole-message
policy). The tests lock in the shape detection so a regression here
surfaces fast — the two consumers no longer duplicate the detectors.
"""

from __future__ import annotations

import pytest

from log_dashboard.credential_patterns import (
    JWT_SHAPE_PATTERN,
    SENSITIVE_KEYWORDS,
    contains_sensitive_keyword,
)


class TestJWTShapePattern:
    def test_matches_three_segment_base64url_token(self) -> None:
        token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIiwiaWF0IjoxNTE2MjM5MDIyfQ"
            ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        assert JWT_SHAPE_PATTERN.search(token) is not None

    def test_does_not_match_short_dotted_string(self) -> None:
        # Real version strings + module paths shouldn't trigger.
        assert JWT_SHAPE_PATTERN.search("v1.2.3") is None
        assert JWT_SHAPE_PATTERN.search("log_dashboard.agitator.runs") is None

    def test_does_not_match_two_segment_token(self) -> None:
        # Needs THREE base64url segments — two should not match.
        two_seg = "a" * 25 + "." + "b" * 25
        assert JWT_SHAPE_PATTERN.search(two_seg) is None


class TestContainsSensitiveKeyword:
    @pytest.mark.parametrize("text", SENSITIVE_KEYWORDS)
    def test_matches_each_keyword_lowercase(self, text: str) -> None:
        assert contains_sensitive_keyword(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "Authorization: Bearer abc",
            "X-API-Key: foo",
            "user provided their PASSWORD",
            "BEARER token-here",
        ],
    )
    def test_matches_mixed_case(self, text: str) -> None:
        assert contains_sensitive_keyword(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "request timed out after 5 seconds",
            "scenario completed with 4 successes",
            "claim CLM-0042 not found",
            "",
        ],
    )
    def test_clean_strings_pass(self, text: str) -> None:
        assert contains_sensitive_keyword(text) is False


class TestSharedVocabulary:
    def test_keywords_are_lowercased(self) -> None:
        # The substring check folds the input to lowercase; the vocabulary
        # itself must be lowercase too so the .lower()-in comparison works.
        for keyword in SENSITIVE_KEYWORDS:
            assert keyword == keyword.lower()

    def test_keyword_set_is_stable(self) -> None:
        # If this assertion fails, _sanitize_error's tests likely need
        # updating too — coordinate the change.
        assert set(SENSITIVE_KEYWORDS) == {
            "authorization",
            "bearer",
            "x-api-key",
            "password",
        }
