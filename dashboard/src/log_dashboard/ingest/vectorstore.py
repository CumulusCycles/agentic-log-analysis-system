"""Chroma + OpenAI embeddings client factory + upsert + lookup helpers."""

from __future__ import annotations

import os
import sys
from collections import Counter
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from log_dashboard.config import Settings
from log_dashboard.ingest.embeddings import (
    make_doc_id,
    make_metadata,
    make_page_content,
)
from log_dashboard.logging_setup import get_logger
from log_dashboard.schemas import LogEntry, LogLevel

log = get_logger("vectorstore")


# Strings we treat as "operator hasn't set this yet" — the same prefixes the
# `.env.example` template uses for placeholder values.
_PLACEHOLDER_PREFIXES = ("your_", "change_me")


def is_embeddings_disabled(settings: Settings) -> bool:
    """True when `OPENAI_API_KEY` is empty or still the .env.example placeholder.

    The dashboard must stay usable for `/api/logs` and `/api/status` even
    without an OpenAI key (ADR-006 spirit). When disabled, the lifespan skips
    backfill + watcher, and `/api/logs/search` returns 503.
    """
    return _looks_like_placeholder(settings.openai_api_key)


def configure_langsmith(settings: Settings) -> None:
    """Programmatically enable LangSmith tracing when the API key looks real.

    LangChain auto-tracing requires BOTH `LANGSMITH_TRACING=true` and
    `LANGSMITH_API_KEY` in the process env. We set TRACING here so operators
    only need to provide the key.
    """
    if _looks_like_placeholder(settings.langsmith_api_key):
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project


def build_vectorstore(
    settings: Settings,
    *,
    client: chromadb.ClientAPI | None = None,
    embedding_function: object | None = None,
) -> Chroma:
    """Construct a langchain-chroma store wrapping the live `chroma` server.

    Tests pass `client=chromadb.Client()` (in-memory) and a stub
    `embedding_function` to avoid network + OpenAI calls. Production calls
    with no kwargs to get the live HttpClient + real OpenAI embeddings.
    """
    if embedding_function is None:
        embedding_function = OpenAIEmbeddings(
            api_key=settings.openai_api_key,
            model=settings.openai_embedding_model,
        )
    if client is None:
        host, port = _parse_chroma_url(settings.chroma_url)
        client = chromadb.HttpClient(host=host, port=port)
    return Chroma(
        client=client,
        collection_name=settings.chroma_collection,
        embedding_function=embedding_function,
    )


def upsert_entries(
    store: Chroma,
    entries: list[LogEntry],
    *,
    batch_size: int = 100,
    dry_run: bool = False,
) -> int:
    """Embed + add entries to the store, batched.

    Before each batch is sent to the embedder, we query Chroma for IDs that
    already exist and skip those — content-stable IDs make this safe and it
    avoids paying OpenAI to re-embed lines we already have. This is the
    difference between a $0.01 restart and a $0 restart.

    When `dry_run=True`, the function short-circuits: no Chroma read, no
    OpenAI call, no upsert. Returns 0 so the caller can log that nothing was
    persisted. Use this from the lifespan when `DASHBOARD_INGEST_DRY_RUN=true`
    to preview ingestion gate behavior without spending any tokens.

    Returns the number of entries actually embedded (excluding dedupes; 0 on
    dry_run).
    """
    if not entries or dry_run:
        return 0
    embedded = 0
    # Tally levels of entries that ACTUALLY hit OpenAI (post-dedup) so the
    # operator-facing summary table shows what was paid for, not what was
    # considered. Per-app — the callers (backfill + watcher) always pass a
    # single-app batch, so `entries[0].app` is the canonical app name.
    level_counts: Counter[str] = Counter()
    app_name = entries[0].app
    for i in range(0, len(entries), batch_size):
        chunk = entries[i : i + batch_size]
        ids = [make_doc_id(e.app, e.raw) for e in chunk]
        existing = store._collection.get(ids=ids, include=[])
        existing_ids = set(existing.get("ids", []))
        new_pairs = [
            (e, doc_id) for e, doc_id in zip(chunk, ids, strict=False) if doc_id not in existing_ids
        ]
        if not new_pairs:
            continue
        new_entries = [pair[0] for pair in new_pairs]
        new_ids = [pair[1] for pair in new_pairs]
        docs = [
            Document(page_content=make_page_content(e), metadata=make_metadata(e))
            for e in new_entries
        ]
        store.add_documents(documents=docs, ids=new_ids)
        embedded += len(new_entries)
        level_counts.update(e.level.value for e in new_entries)
    if embedded > 0:
        _emit_embed_summary(app_name, level_counts, embedded)
    return embedded


# Standard level order for the embed-summary table. Includes every level the
# parser emits even when its count is 0 so the table shape stays consistent
# across calls — easier to scan visually in `docker compose logs`.
_EMBED_SUMMARY_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")


def _emit_embed_summary(app: str, level_counts: Counter[str], total: int) -> None:
    """Log + print a level-count summary after every OpenAI embed call.

    Emits two surfaces:
      1. A structured `embedding_complete` event (JSON via structlog) — the
         dashboard's own ingestion pipeline picks this up like any other
         log line, so the operator can grep for it.
      2. A human-readable ASCII table to stdout — distinct from the JSON
         stream so an operator tailing the container logs sees it at a
         glance after each upsert.

    Per `feedback_never_log_credentials`, neither surface includes the raw
    log lines — only counts.
    """
    counts_dict = dict(level_counts)
    log.info(
        "embedding_complete",
        app=app,
        level_counts=counts_dict,
        total=total,
    )
    # `flush=True` because uvicorn's stdout is line-buffered under Docker and
    # we want the table visible immediately, not buffered behind the next log.
    print(_format_embed_summary(app, level_counts, total), flush=True, file=sys.stdout)


def _format_embed_summary(app: str, level_counts: Counter[str], total: int) -> str:
    """ASCII table — fixed-width so columns align in any terminal."""
    bar = "=" * 56
    sep = "+" + "-" * 9 + "+" + "-" * 9 + "+"
    lines = [
        "",
        bar,
        f" Chroma embedding complete — {app}",
        bar,
        sep,
        f"| {'Level':<7} | {'Count':>7} |",
        sep,
    ]
    for level in _EMBED_SUMMARY_LEVELS:
        count = level_counts.get(level, 0)
        lines.append(f"| {level:<7} | {count:>7} |")
    # Surface any level the parser produced that we don't have a canonical
    # row for (future-proof against e.g. CRITICAL/FATAL being added).
    for level in sorted(level_counts):
        if level not in _EMBED_SUMMARY_LEVELS:
            lines.append(f"| {level:<7} | {level_counts[level]:>7} |")
    lines.append(sep)
    lines.append(f"| {'TOTAL':<7} | {total:>7} |")
    lines.append(sep)
    lines.append(bar)
    lines.append("")
    return "\n".join(lines)


def lookup_entry_by_id(store: Chroma | None, entry_id: str) -> LogEntry | None:
    """Single-entry Chroma lookup by content-hash ID.

    Backs `GET /api/errors/{id}` (Phase 7e PR 4b). Uses the underlying
    `_collection.get(ids=[...])` rather than `similarity_search` because we
    already know the exact key — semantic search here would be wasteful and
    would also require an embedding round-trip just to discard the result.

    Returns None when:
      - `store` is None (OpenAI key missing → embeddings disabled)
      - the ID isn't in the collection (entry never passed the ingest gate)
      - the metadata is malformed (logged + skipped)

    Caller distinguishes "no store" vs "no entry" via the surrounding context
    (the route checks store presence before calling this).
    """
    if store is None:
        return None
    try:
        result = store._collection.get(ids=[entry_id], include=["metadatas"])
    except Exception as exc:  # noqa: BLE001 — Chroma client raises a variety of opaque errors
        log.warning(
            "lookup_entry_by_id_chroma_error",
            entry_id=entry_id,
            error_class=type(exc).__name__,
        )
        return None
    metadatas = result.get("metadatas") or []
    if not metadatas:
        return None
    return metadata_to_log_entry(metadatas[0] or {})


def metadata_to_log_entry(md: dict[str, Any]) -> LogEntry | None:
    """Reconstruct a `LogEntry` from a Chroma metadata dict.

    Single source of truth for the inverse of `make_metadata`. Both
    `routers/search.py` (Document-shaped results) and `lookup_entry_by_id`
    (raw `_collection.get` results) go through this helper so the
    field-mapping rules are not duplicated.

    Returns None on shape error; the caller decides what status to surface.
    """
    try:
        return LogEntry(
            id=str(md.get("id") or ""),
            timestamp=_parse_ts(md.get("timestamp_iso")),
            level=LogLevel(str(md.get("level", "INFO"))),
            app=str(md.get("app") or ""),
            event=str(md.get("event") or ""),
            fields=_fields_from_metadata(md),
            raw=str(md.get("raw") or ""),
        )
    except (ValueError, KeyError, TypeError) as exc:
        log.warning(
            "metadata_to_log_entry_malformed",
            error_class=type(exc).__name__,
        )
        return None


def _parse_ts(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    raise ValueError("missing timestamp_iso")


def _fields_from_metadata(md: dict[str, Any]) -> dict[str, Any]:
    """Recover the small subset of `fields` we duplicated into metadata.

    Chroma metadata is scalars-only, so the full `fields` dict cannot be
    round-tripped. `raw` on the LogEntry preserves the original line for the
    Error Detail screen.
    """
    out: dict[str, Any] = {}
    logger_name = md.get("logger")
    if isinstance(logger_name, str) and logger_name:
        out["logger"] = logger_name
    if md.get("has_stack_trace"):
        out["has_stack_trace"] = True
    return out


def _parse_chroma_url(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    return parsed.hostname or "chroma", parsed.port or 8000


def _looks_like_placeholder(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    return any(stripped.startswith(p) for p in _PLACEHOLDER_PREFIXES)
