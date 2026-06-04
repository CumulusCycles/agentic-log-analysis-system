"""POST /api/logs/search — semantic search over the Chroma-backed log embeddings."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth.jwt import get_current_admin
from ..ingest.spec import APP_NAMES
from ..logging_setup import get_logger
from ..schemas import LogEntry, LogLevel, LogsSearchRequest, LogsSearchResponse

if TYPE_CHECKING:
    from langchain_chroma import Chroma
    from langchain_core.documents import Document

router = APIRouter(tags=["search"])
log = get_logger("search")

# Don't dump the entire query into the log line — a paragraph-long search
# would balloon the log file. The query itself isn't a credential (admin
# input), but the truncation keeps the log line bounded.
_QUERY_LOG_LIMIT = 200


@router.post("/logs/search", response_model=LogsSearchResponse)
async def search_logs(
    body: LogsSearchRequest,
    request: Request,
    _: dict[str, Any] = Depends(get_current_admin),
) -> LogsSearchResponse:
    store: Chroma | None = getattr(request.app.state, "vectorstore", None)
    if store is None:
        # Degraded mode: OpenAI key missing/placeholder. /api/logs and /api/status
        # still work — only semantic search is unavailable.
        log.info(
            "search_unavailable_no_embeddings",
            query_preview=_truncate(body.query),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="semantic search is unavailable — OPENAI_API_KEY is not configured",
        )

    _validate_apps(body.apps)
    where = _build_where(body)

    log.info(
        "search_started",
        query_preview=_truncate(body.query),
        top_k=body.top_k,
        has_filter=where is not None,
    )

    results = await asyncio.to_thread(
        store.similarity_search_with_score,
        body.query,
        k=body.top_k,
        filter=where,
    )

    entries: list[LogEntry] = []
    scores: list[float] = []
    for doc, score in results:
        entry = _document_to_entry(doc)
        if entry is None:
            continue
        entries.append(entry)
        scores.append(float(score))

    log.info(
        "search_complete",
        query_preview=_truncate(body.query),
        result_count=len(entries),
    )
    return LogsSearchResponse(entries=entries, scores=scores)


def _validate_apps(apps: list[str] | None) -> None:
    if not apps:
        return
    invalid = [a for a in apps if a not in APP_NAMES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown app(s): {','.join(invalid)}",
        )


def _build_where(req: LogsSearchRequest) -> dict[str, Any] | None:
    """Translate the request filters into a Chroma `$where` clause.

    Chroma requires `$and` only when multiple clauses are combined; a single
    clause is passed by itself.
    """
    clauses: list[dict[str, Any]] = []
    if req.apps:
        clauses.append({"app": {"$in": req.apps}})
    if req.levels:
        clauses.append({"level": {"$in": [lvl.value for lvl in req.levels]}})
    if req.since is not None:
        clauses.append({"timestamp_epoch": {"$gte": req.since.timestamp()}})
    if req.before is not None:
        clauses.append({"timestamp_epoch": {"$lt": req.before.timestamp()}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _document_to_entry(doc: Document) -> LogEntry | None:
    """Reconstruct a `LogEntry` from a Chroma `Document`. The metadata schema
    is the one written by `ingest.embeddings.make_metadata`."""
    md = doc.metadata or {}
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
            "search_skip_malformed_doc",
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
    """Recover the small subset of `fields` we stored in metadata.

    We don't round-trip the full `fields` dict (Chroma metadata is scalars-only),
    only the items we duplicated at ingestion time. The `raw` field on the
    LogEntry preserves the original line — 7e's Error Detail screen will use
    that for the full picture.
    """
    out: dict[str, Any] = {}
    logger = md.get("logger")
    if isinstance(logger, str) and logger:
        out["logger"] = logger
    if md.get("has_stack_trace"):
        # We don't store the trace itself; flag presence so the UI knows.
        out["has_stack_trace"] = True
    return out


def _truncate(text: str) -> str:
    if len(text) <= _QUERY_LOG_LIMIT:
        return text
    return text[:_QUERY_LOG_LIMIT] + "…"
