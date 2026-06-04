"""Pure-function helpers that shape a LogEntry into a Chroma Document.

No I/O here — keeps the embedding contract testable without spinning up
Chroma or hitting OpenAI. Imported by vectorstore.py, backfill.py, watcher.py.
"""

import hashlib
from collections.abc import Iterable
from typing import Any

from log_dashboard.schemas import LogEntry, LogLevel


def make_doc_id(app: str, raw: str) -> str:
    """Content-stable Chroma document ID: `{app}:{sha1(raw)[:16]}`.

    Stable across runs so re-embedding the same line is a no-op upsert.
    16 hex chars (64 bits) is overkill for the ~10^5 doc count this project
    sees — birthday collisions need ~10^9 docs.
    """
    digest = hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"{app}:{digest[:16]}"


def make_page_content(entry: LogEntry) -> str:
    """Embeddable string. Render `event` + sorted fields in a natural-language-ish
    way (no JSON brackets) because the embedder is trained on prose, not JSON
    syntax. Long field values are truncated at 200 chars to keep the token
    cost predictable.
    """
    lines = [f"[{entry.app}] level={entry.level.value} event={entry.event}"]
    for key in sorted(entry.fields.keys()):
        val = entry.fields[key]
        s = val if isinstance(val, str) else str(val)
        if len(s) > 200:
            s = s[:200] + "…"
        lines.append(f"  {key}={s}")
    return "\n".join(lines)


def make_metadata(entry: LogEntry) -> dict[str, Any]:
    """Chroma metadata. Scalars only (str / int / float / bool) — that's the
    Chroma constraint. `timestamp_epoch` enables `$gte` / `$lt` range filters;
    `raw` is duplicated here so 7e's Error Detail can fetch the original line
    without re-reading the source file.
    """
    return {
        "id": entry.id,
        "app": entry.app,
        "level": entry.level.value,
        "event": entry.event,
        "source": entry.source,
        "timestamp_epoch": entry.timestamp.timestamp(),
        "timestamp_iso": entry.timestamp.isoformat(),
        "logger": str(entry.fields.get("logger", "")),
        "has_stack_trace": "stack_trace" in entry.fields,
        "raw": entry.raw,
    }


def filter_for_ingest(
    entries: Iterable[LogEntry],
    *,
    levels: frozenset[LogLevel],
    sources: frozenset[str],
) -> list[LogEntry]:
    """The single gate that decides what enters the embedding pipeline.

    An entry is kept iff its level is in `levels` AND its source is in
    `sources`. Defaults (from `Settings`) keep only PROD WARN/ERROR — the
    smallest signal-rich slice. The operator-facing `/api/logs` view is
    UNAFFECTED (it reads volumes directly, never touches this).
    """
    return [e for e in entries if e.level in levels and e.source in sources]
