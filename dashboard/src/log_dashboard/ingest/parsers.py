"""Per-format log line parsers.

Each parser returns a `LogEntry` on success or `None` on a malformed line.
None is a signal — the caller filters it out without surfacing the bad line.
Parser errors are NEVER allowed to log the raw line itself (per
`feedback_never_log_credentials`) because an upstream app's bug could put a
bearer token or secret in the log.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from ..schemas import LogEntry, LogLevel
from .embeddings import make_doc_id
from .spec import LogFormat

# Logback default pattern: `YYYY-MM-DD HH:mm:ss.SSS LEVEL --- [thread] class : message`
# Level is right-padded to 5 chars so INFO/WARN have two trailing spaces before `---`.
_LOGBACK_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+"
    r"(?P<level>DEBUG|INFO|WARN|ERROR|TRACE)\s+---\s+"
    r"\[(?P<thread>[^\]]+)\]\s+"
    r"(?P<logger>\S+)\s+:\s+"
    r"(?P<message>.*)$"
)

# key=value parser for Logback messages. Values run until the next `<space><word>=`
# or end-of-line, so `detail=invalid credentials` works.
_KV_RE = re.compile(r"(\w+)=(.*?)(?=\s+\w+=|$)")

# Paths that the Docker healthcheck or operational probes hit.
# Any `event=request path=<HEALTH_PATH>` line gets tagged `source=health`
# and is excluded from the embedding gate by default. Operator view
# (`/api/logs`) is unaffected.
_HEALTH_PATHS = frozenset({"/health", "/api/health", "/actuator/health"})


def _infer_source(
    *,
    explicit: object | None,
    event: str,
    path: object | None,
) -> str:
    """Derive the `source` tag for a parsed entry.

    Precedence:
      1. If the line is a healthcheck request, tag `health` — this is an
         immutable property of the request that no header can override.
      2. Otherwise honour the explicit `source` value (set by each app's
         request-logger middleware via `structlog.contextvars` /
         `AsyncLocalStorage` / `MDC` from the inbound `X-Source` per ADR-011
         — propagated cross-app via the outbound HTTP clients).
      3. Fall back to `unknown`. Missing source is a code smell once the
         X-Source propagation chain ships everywhere — usually a non-request
         event (startup / scheduled task) or a regression in one of the
         per-app logging plumbings. The dashboard surfaces `unknown` in the
         UI so the operator can spot leaks; the ingest gate admits it
         alongside `prod`/`synthetic` (`DASHBOARD_INGEST_SOURCES` default
         widens to include `unknown` so visibility is preserved).
    """
    if event == "request" and isinstance(path, str) and path in _HEALTH_PATHS:
        return "health"
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    return "unknown"


def _normalize_level(raw: str | None) -> LogLevel | None:
    if not raw:
        return None
    upper = raw.upper()
    if upper == "WARNING":
        return LogLevel.WARN
    if upper in ("TRACE",):  # collapse Logback TRACE → DEBUG for our enum
        return LogLevel.DEBUG
    try:
        return LogLevel(upper)
    except ValueError:
        return None


def _parse_timestamp(raw: str | None, *, assume_utc: bool = False) -> datetime | None:
    """Parse an ISO 8601 timestamp. SDA/FNOL/CP have explicit Z; AP has none."""
    if not raw:
        return None
    s = raw
    if assume_utc:
        # Logback: "2026-06-04 16:30:59.220" → make tz-aware in UTC.
        s = s.replace(" ", "T") + "+00:00"
    else:
        # structlog/winston end with Z which fromisoformat handles since 3.11.
        s = s.replace("Z", "+00:00") if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _make_entry(
    *,
    app: str,
    seq: int,
    timestamp: datetime,
    level: LogLevel,
    event: str,
    fields: dict[str, Any],
    raw: str,
    source: str,
) -> LogEntry:
    # `seq` is retained on the parser API as a caller-side counter for
    # diagnostics; the LogEntry.id itself is content-hash-derived so a
    # /errors/{id} URL is stable across requests and matches the Chroma
    # document ID. PR 4b (Phase 7e).
    del seq
    return LogEntry(
        id=make_doc_id(app=app, raw=raw),
        timestamp=timestamp,
        level=level,
        app=app,
        event=event,
        fields=fields,
        raw=raw,
        source=source,
    )


def parse_structlog_line(*, app: str, seq: int, line: str) -> LogEntry | None:
    """Parse one structlog/ProcessorFormatter JSON line (SDA + FNOL)."""
    line = line.rstrip("\n")
    if not line:
        return None
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    level = _normalize_level(payload.get("level"))
    timestamp = _parse_timestamp(payload.get("timestamp"))
    event = payload.get("event")
    if level is None or timestamp is None or not isinstance(event, str):
        return None
    fields = {
        k: v for k, v in payload.items() if k not in ("level", "timestamp", "event", "source")
    }
    source = _infer_source(explicit=payload.get("source"), event=event, path=payload.get("path"))
    return _make_entry(
        app=app,
        seq=seq,
        timestamp=timestamp,
        level=level,
        event=event,
        fields=fields,
        raw=line,
        source=source,
    )


def parse_winston_line(*, app: str, seq: int, line: str) -> LogEntry | None:
    """Parse one winston JSON line (Customer Portal).

    Winston emits both `event` and `message`; for request lines both hold
    `"request"`. We prefer `event` and fall back to `message`.
    """
    line = line.rstrip("\n")
    if not line:
        return None
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    level = _normalize_level(payload.get("level"))
    timestamp = _parse_timestamp(payload.get("timestamp"))
    event = payload.get("event") or payload.get("message")
    if level is None or timestamp is None or not isinstance(event, str):
        return None
    fields = {
        k: v
        for k, v in payload.items()
        if k not in ("level", "timestamp", "event", "message", "source")
    }
    source = _infer_source(explicit=payload.get("source"), event=event, path=payload.get("path"))
    return _make_entry(
        app=app,
        seq=seq,
        timestamp=timestamp,
        level=level,
        event=event,
        fields=fields,
        raw=line,
        source=source,
    )


def parse_logback_line(*, app: str, seq: int, line: str) -> LogEntry | None:
    """Parse one Logback text-pattern line (Agent Portal).

    Returns None on a continuation line (no timestamp prefix) — the reader is
    responsible for folding continuations into the previous entry's stack
    trace. Returns None on a malformed line as well; the caller cannot tell
    the difference, which is fine because both are dropped.
    """
    line = line.rstrip("\n")
    if not line:
        return None
    m = _LOGBACK_RE.match(line)
    if m is None:
        return None
    level = _normalize_level(m.group("level"))
    timestamp = _parse_timestamp(m.group("ts"), assume_utc=True)
    if level is None or timestamp is None:
        return None
    message = m.group("message")
    # Event = first whitespace-delimited token of the message. This works for
    # both kv-style lines (`request method=GET ...` → `request`) and free-form
    # one-liners (`Started AgentPortalApplication in 3.21s` → `Started`).
    # Empty messages fall back to the logger basename so dashboards still
    # bucket them.
    first_token = message.split(None, 1)
    if first_token:
        event = first_token[0]
    else:
        event = m.group("logger").rsplit(".", 1)[-1]
    fields: dict[str, Any] = {
        "thread": m.group("thread"),
        "logger": m.group("logger"),
    }
    for k, v in _KV_RE.findall(message):
        fields[k] = v.strip()
    # Preserve the free-form message tail when there are no kv pairs so the
    # event token doesn't lose context.
    if not _KV_RE.search(message) and len(first_token) > 1:
        fields["message"] = message
    # `source` is parsed into fields via the kv loop above. Move it out — it
    # belongs on the LogEntry itself, not in the heterogeneous `fields` bag.
    explicit_source = fields.pop("source", None)
    source = _infer_source(explicit=explicit_source, event=event, path=fields.get("path"))
    return _make_entry(
        app=app,
        seq=seq,
        timestamp=timestamp,
        level=level,
        event=event,
        fields=fields,
        raw=line,
        source=source,
    )


def parse_line(*, fmt: LogFormat, app: str, seq: int, line: str) -> LogEntry | None:
    """Dispatch to the per-format parser."""
    if fmt is LogFormat.STRUCTLOG_JSON:
        return parse_structlog_line(app=app, seq=seq, line=line)
    if fmt is LogFormat.WINSTON_JSON:
        return parse_winston_line(app=app, seq=seq, line=line)
    if fmt is LogFormat.LOGBACK_TEXT:
        return parse_logback_line(app=app, seq=seq, line=line)
    return None
