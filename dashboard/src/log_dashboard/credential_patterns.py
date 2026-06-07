"""Shared credential-detection primitives.

Used by `credentials.py` (surgical substitute policy — replace the
secret-shaped span with `[REDACTED]`, keep surrounding text) and
`agitator/runs.py::_sanitize_error` (drop-whole-message policy — return
a sentinel string when anything secret-shaped is present).

Each consumer keeps its own policy; this module owns the shape detection
so the two cannot drift over time.
"""

from __future__ import annotations

import re

__all__ = [
    "JWT_SHAPE_PATTERN",
    "SENSITIVE_KEYWORDS",
    "contains_sensitive_keyword",
]

JWT_SHAPE_PATTERN: re.Pattern[str] = re.compile(
    r"[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}"
)

SENSITIVE_KEYWORDS: tuple[str, ...] = (
    "authorization",
    "bearer",
    "x-api-key",
    "password",
)


def contains_sensitive_keyword(text: str) -> bool:
    """Case-insensitive substring match against `SENSITIVE_KEYWORDS`."""
    lower = text.lower()
    return any(needle in lower for needle in SENSITIVE_KEYWORDS)
