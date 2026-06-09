"""GET /api/chroma/stats — aggregated stats over the embedded corpus.

Operator-facing diagnostic. Answers "what's actually in Chroma?" in one
call. Reuses the dashboard's `app.state.vectorstore`; never invokes the
LLM or embedder.

Aggregation strategy: a single `_collection.get(include=["metadatas"])`
pulls every doc's metadata in one Chroma RPC, then we count in Python.
At today's corpus sizes (<10k docs) this is sub-50ms. At 100k+ docs the
single-call shape becomes a few seconds — fine for an admin diagnostic
tab. If the corpus grows past that, the future fix is `limit`+`offset`
pagination on the get call, not adding a server-side aggregation layer.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..auth.jwt import get_current_admin
from ..config import Settings, get_settings
from ..logging_setup import get_logger
from ..schemas import ChromaFlushResponse, ChromaStatsResponse, DayCount, EventCount

router = APIRouter(tags=["chroma-stats"])
log = get_logger("chroma_stats")

# nomic-embed-text returns 768-dim vectors (Phase 8 / ADR-017). The
# dashboard pins this via `DASHBOARD_EMBED_MODEL` in .env.example;
# changing the model requires wiping the collection (different dims,
# vectors aren't comparable).
_EMBEDDING_DIMENSIONS = 768

# Top-N caps for the breakdowns. Bar charts beyond these N values become
# unreadable; the operator can drill into the Log Explorer for the long tail.
_TOP_EVENTS = 10
# Default by-day window when neither `since` nor `until` are passed. The UI
# now drives this via the TimeWindowSelector and defaults to 7d; the 30-day
# fallback only applies to callers who don't pass either bound (Swagger, raw
# curl, older clients).
_DEFAULT_DAYS_WINDOW = 30


@router.get("/chroma/stats", response_model=ChromaStatsResponse)
async def get_chroma_stats(
    request: Request,
    since: Annotated[
        datetime | None,
        Query(
            description=(
                "Scope the `by_day` aggregation to entries with timestamp >= this value. "
                "Other buckets (by_app, by_level, by_source, by_event) stay unscoped."
            ),
        ),
    ] = None,
    until: Annotated[
        datetime | None,
        Query(
            description=(
                "Scope the `by_day` aggregation to entries with timestamp < this value. "
                "Other buckets (by_app, by_level, by_source, by_event) stay unscoped."
            ),
        ),
    ] = None,
    _: dict[str, Any] = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> ChromaStatsResponse:
    """Return aggregated stats over the Chroma collection.

    Returns 503 when the vectorstore is not configured (degraded mode
    when Ollama is unreachable) — same posture as `GET /api/errors/{id}`.

    `since` + `until` scope the `by_day` series only. Whole-corpus rollups
    (by_app / by_level / by_source / by_event) stay unscoped because the
    operator's mental model for those buckets is "what's actually embedded"
    — narrowing them by date is a different question best served by the
    Log Explorer's filtered view.
    """
    store = getattr(request.app.state, "vectorstore", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vectorstore unavailable",
        )

    now = datetime.now(tz=UTC)
    try:
        total = store._collection.count()  # noqa: SLF001 — Chroma exposes no public count
    except Exception as exc:  # noqa: BLE001
        log.warning("chroma_stats_count_failed", error_class=type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vectorstore unavailable",
        ) from exc

    if total == 0:
        # by_day still emits a continuous-axis window with zeros so the UI's
        # bar chart x-axis stays continuous on a freshly-cleared corpus.
        return ChromaStatsResponse(
            total_count=0,
            by_app={},
            by_level={},
            by_source={},
            by_event=[],
            by_day=_count_by_day([], since=since, until=until, now=now),
            embedding_model=settings.dashboard_embed_model,
            dimensions=_EMBEDDING_DIMENSIONS,
            as_of=now,
        )

    try:
        # include=["metadatas"] returns IDs + metadata dicts; no documents,
        # no embeddings — minimal payload over the wire.
        rows = store._collection.get(include=["metadatas"])  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        log.warning("chroma_stats_get_failed", error_class=type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vectorstore unavailable",
        ) from exc

    metadatas: list[dict[str, Any]] = rows.get("metadatas") or []

    return ChromaStatsResponse(
        total_count=total,
        by_app=_count_by_key(metadatas, "app"),
        by_level=_count_by_key(metadatas, "level"),
        by_source=_count_by_key(metadatas, "source"),
        by_event=_top_events(metadatas, n=_TOP_EVENTS),
        by_day=_count_by_day(metadatas, since=since, until=until, now=now),
        embedding_model=settings.dashboard_embed_model,
        dimensions=_EMBEDDING_DIMENSIONS,
        as_of=now,
    )


# Maximum IDs we'll feed to a single `_collection.delete(ids=...)` call.
# Chroma accepts large lists but very-large payloads can stress the HTTP
# client; batching keeps the per-request body bounded.
_FLUSH_DELETE_BATCH_SIZE = 1000


@router.post("/chroma/flush", response_model=ChromaFlushResponse)
async def flush_chroma(
    request: Request,
    _: dict[str, Any] = Depends(get_current_admin),
) -> ChromaFlushResponse:
    """Delete every document in the Chroma collection.

    Operator-driven. Used to reset the corpus before a fresh backfill or to
    free vector storage after a problematic ingest run. Returns 503 when the
    vectorstore is not configured.

    After flush, the collection is empty but still exists with the same name
    and embedding model — the langchain-chroma wrapper on `app.state.vectorstore`
    keeps working. Re-populating requires `docker compose restart log-dashboard`;
    the lifespan's backfill task only runs at startup.
    """
    store = getattr(request.app.state, "vectorstore", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vectorstore unavailable",
        )

    now = datetime.now(tz=UTC)
    try:
        # Pull every ID without metadata or embeddings — minimal payload.
        rows = store._collection.get(include=[])  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        log.warning("chroma_flush_get_failed", error_class=type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vectorstore unavailable",
        ) from exc

    ids: list[str] = list(rows.get("ids") or [])
    deleted = len(ids)

    if deleted == 0:
        log.info("chroma_flush_complete", deleted=0)
        return ChromaFlushResponse(deleted_count=0, as_of=now)

    try:
        for i in range(0, deleted, _FLUSH_DELETE_BATCH_SIZE):
            batch = ids[i : i + _FLUSH_DELETE_BATCH_SIZE]
            store._collection.delete(ids=batch)  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "chroma_flush_delete_failed",
            error_class=type(exc).__name__,
            attempted=deleted,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vectorstore unavailable",
        ) from exc

    log.info("chroma_flush_complete", deleted=deleted)
    return ChromaFlushResponse(deleted_count=deleted, as_of=now)


def _count_by_key(metadatas: list[dict[str, Any]], key: str) -> dict[str, int]:
    """Count metadatas grouped by `key`. Missing values bucket to "unknown"."""
    counter: Counter[str] = Counter()
    for meta in metadatas:
        value = meta.get(key)
        bucket = value if isinstance(value, str) and value else "unknown"
        counter[bucket] += 1
    # Sort by descending count, then alphabetical for stable rendering.
    return dict(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0])))


def _top_events(metadatas: list[dict[str, Any]], *, n: int) -> list[EventCount]:
    """Return the top-N event names by count, descending."""
    counter: Counter[str] = Counter()
    for meta in metadatas:
        event = meta.get("event")
        if isinstance(event, str) and event:
            counter[event] += 1
    return [EventCount(event=e, count=c) for e, c in counter.most_common(n)]


def _count_by_day(
    metadatas: list[dict[str, Any]],
    *,
    since: datetime | None,
    until: datetime | None,
    now: datetime,
) -> list[DayCount]:
    """Bucket metadatas by UTC date over a `[since, until)` window, ascending.

    When neither bound is provided, defaults to the last
    `_DEFAULT_DAYS_WINDOW` calendar days ending TODAY (matches the pre-PR-2
    `/api/chroma/stats` contract — 30 rows, today is the last). When at
    least one bound is provided, the operator's instants drive both the
    epoch filter AND the inclusive date series.

    Days with zero entries appear in the response so the UI's bar chart
    has a continuous x-axis. `timestamp_epoch` is the canonical sort key
    (set by `make_metadata` at embed time).
    """
    default_mode = since is None and until is None

    # 1. Epoch filter on the entries.
    if default_mode:
        start_epoch: float = (now - timedelta(days=_DEFAULT_DAYS_WINDOW)).timestamp()
        end_epoch: float | None = None
    else:
        # Inverted-range guard: emit an empty series rather than silently
        # swallowing the operator's mistake. UI sees the misconfiguration.
        if since is not None and until is not None and until <= since:
            return []
        start_epoch = since.timestamp() if since is not None else float("-inf")
        end_epoch = until.timestamp() if until is not None else None

    counter: Counter[str] = Counter()
    for meta in metadatas:
        ts = meta.get("timestamp_epoch")
        if not isinstance(ts, int | float):
            continue
        if ts < start_epoch:
            continue
        if end_epoch is not None and ts >= end_epoch:
            continue
        date_str = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
        counter[date_str] += 1

    # 2. Continuous-axis date series.
    if default_mode:
        # 30 rows, today on the end — preserves the pre-PR-2 contract.
        today = now.astimezone(UTC).date()
        series: list[DayCount] = []
        for offset in range(_DEFAULT_DAYS_WINDOW - 1, -1, -1):
            day = today - timedelta(days=offset)
            date_str = day.strftime("%Y-%m-%d")
            series.append(DayCount(date=date_str, count=counter.get(date_str, 0)))
        return series

    # Operator-supplied bounds — enumerate inclusively from start_date to
    # end_date so the chart axis matches the operator's stated window.
    window_start = since if since is not None else now - timedelta(days=_DEFAULT_DAYS_WINDOW)
    window_end = until if until is not None else now
    start_date = window_start.astimezone(UTC).date()
    end_date = window_end.astimezone(UTC).date()
    # Bound at 366 days so a pathological window can't generate a runaway response.
    span_days = min((end_date - start_date).days + 1, 366)
    span_days = max(span_days, 1)

    series = []
    for offset in range(span_days):
        day = start_date + timedelta(days=offset)
        if day > end_date:
            break
        date_str = day.strftime("%Y-%m-%d")
        series.append(DayCount(date=date_str, count=counter.get(date_str, 0)))
    return series
