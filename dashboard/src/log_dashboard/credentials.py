"""Credential-redaction helpers for the LangGraph agent path.

Two-layer defence against credentials reaching OpenAI / LangSmith / chat
responses:

1. `sanitize_user_input` — strip secret-shaped substrings from a user's chat
   message BEFORE it enters the graph or any LangSmith trace.
2. `sanitize_log_raw` — strip secret-shaped substrings from a log line's
   `raw` field BEFORE it lands in the LLM's tool-message context.

Both operate by surgical substitution (`replace the secret-shaped span with
`[REDACTED]`, keep the surrounding text`) rather than dropping the whole
message — the LLM still needs the conversational + log context to reason.
The Agitator's `_sanitize_error` (`agitator/runs.py`) keeps its drop-the-
whole-message stance for error strings; the shared shape detection (JWT
pattern + keyword vocabulary) now lives in `credential_patterns.py` so the
two consumers cannot drift.

Matched shapes (each one is a separate compiled regex so we can attribute
which class redacted what in tests):

* `Authorization: Bearer <token>` and bare `Bearer <token>`
* `X-API-Key: <key>`
* `password=<value>` / `password: <value>` / `"password": "<value>"`
* JWT-shaped three-segment tokens (≥20 base64url chars per segment)
* DSN connection strings with embedded credentials
  (`scheme://user:pass@host`) — covers postgres, postgresql, mongodb,
  mongodb+srv, mysql, mariadb, redis, amqp, amqps
"""

from __future__ import annotations

import re

from .credential_patterns import JWT_SHAPE_PATTERN

__all__ = ["sanitize_user_input", "sanitize_log_raw"]

_REDACTED = "[REDACTED]"

# Hard cap on the size we'll process; truncate larger inputs after sanitising
# the head so a giant blob can never become a runaway regex problem.
_MAX_INPUT_LEN = 8000

# `Authorization: Bearer <token>` or `authorization: bearer <token>`,
# case-insensitive. The token is any non-whitespace run.
_AUTH_BEARER = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+)\S+",
)

# Bare `Bearer <token>` not preceded by `authorization:` — catches the case
# where the operator pastes a curl `-H 'Bearer ...'` snippet.
_BARE_BEARER = re.compile(
    r"(?i)\bbearer\s+([A-Za-z0-9_\-\.]{20,})",
)

# `X-API-Key: <key>` (header form).
_API_KEY_HEADER = re.compile(
    r"(?i)(x-api-key\s*[:=]\s*)\S+",
)

# `password=value`, `password: value`, `"password": "value"`. The optional
# quotes around the key handle JSON form (`"password"`); the optional opening
# quote on the value handles both JSON form and YAML/env-style. Stops at the
# first whitespace, comma, brace, bracket, or quote so JSON contexts work.
_PASSWORD = re.compile(
    r"(?i)(\"?password\"?\s*[:=]\s*\"?)[^\s,}\]\"']+",
)

# Three base64url-ish segments separated by dots — shared with
# `agitator/runs.py::_sanitize_error` via `credential_patterns`.
_JWT_SHAPE = JWT_SHAPE_PATTERN

# DSN with embedded credentials: `scheme://user:pass@host`. We don't need to
# match every scheme — only ones we'd realistically see in this project's
# logs or env (per `.env.example`).
_DSN_WITH_CREDS = re.compile(
    r"(?i)\b(postgres|postgresql|mongodb(?:\+srv)?|mysql|mariadb|redis|amqp|amqps)://"
    r"([^:/\s@]+):([^@/\s]+)@",
)

# Order matters: `_AUTH_BEARER` must run before `_BARE_BEARER` so the header
# form's full match wins; otherwise the bare pattern would only redact the
# token-after-`Bearer`, leaving the `Authorization:` keyword behind in the
# output. `_JWT_SHAPE` runs last so it catches stray tokens missed above.
_REDACTORS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_AUTH_BEARER, rf"\1{_REDACTED}"),
    (_API_KEY_HEADER, rf"\1{_REDACTED}"),
    (_PASSWORD, rf"\1{_REDACTED}"),
    (_DSN_WITH_CREDS, rf"\1://\2:{_REDACTED}@"),
    (_BARE_BEARER, rf"bearer {_REDACTED}"),
    (_JWT_SHAPE, _REDACTED),
)


def _apply(text: str) -> str:
    """Run all redactors over `text`. Returns the sanitised string."""
    out = text
    for pattern, replacement in _REDACTORS:
        out = pattern.sub(replacement, out)
    return out


def sanitize_user_input(message: str) -> str:
    """Surgical redaction for a user-supplied chat message.

    Run BEFORE the message enters the LangGraph state — every downstream
    consumer (LangSmith trace, LLM context, response body) sees the
    sanitised form.

    Truncates inputs above `_MAX_INPUT_LEN` after redaction to bound work
    on enormous pastes (e.g. an operator dumps a 1MB log file into the
    chat box).
    """
    if not message:
        return ""
    sanitised = _apply(message[:_MAX_INPUT_LEN])
    if len(message) > _MAX_INPUT_LEN:
        sanitised = sanitised + "…"
    return sanitised


def sanitize_log_raw(raw: str) -> str:
    """Surgical redaction for a log line's `raw` field.

    Run BEFORE the line lands in a `ToolMessage` payload. Defence-in-depth
    against logs that slipped a token past the per-app audit baseline
    (`.claude/rules/logging.md` §Non-Negotiable Rules #2). The LLM never
    sees the secret; LangSmith never traces it; the chat response cannot
    echo it.
    """
    if not raw:
        return ""
    return _apply(raw[:_MAX_INPUT_LEN])
