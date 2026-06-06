"""GET /api/chroma/stats — aggregated stats over the embedded corpus.

Operator-facing diagnostic. Answers "what's actually in Chroma?" in one
call. Reuses the dashboard's `app.state.vectorstore`; never hits OpenAI.

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
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth.jwt import get_current_admin
from ..config import Settings, get_settings
from ..logging_setup import get_logger
from ..schemas import ChromaStatsResponse, DayCount, EventCount

router = APIRouter(tags=["chroma-stats"])
log = get_logger("chroma_stats")

# text-embedding-3-small returns 1536-dim vectors. The dashboard pins this
# model via `OPENAI_EMBEDDING_MODEL` in .env.example; changing the model
# requires wiping the collection (different dims, vectors aren't comparable).
_EMBEDDING_DIMENSIONS = 1536

# Top-N caps for the breakdowns. Bar charts beyond these N values become
# unreadable; the operator can drill into the Log Explorer for the long tail.
_TOP_EVENTS = 10
_DAYS_WINDOW = 30


@router.get("/chroma/stats", response_model=ChromaStatsResponse)
async def get_chroma_stats(
    request: Request,
    _: dict[str, Any] = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> ChromaStatsResponse:
    """Return aggregated stats over the Chroma collection.

    Returns 503 when the vectorstore is not configured (degraded mode with
    placeholder OpenAI key) — same posture as `GET /api/errors/{id}`.
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
        # by_day still emits the 30-day window with zeros so the UI's bar
        # chart x-axis stays continuous on a freshly-cleared corpus.
        return ChromaStatsResponse(
            total_count=0,
            by_app={},
            by_level={},
            by_source={},
            by_event=[],
            by_day=_count_by_day([], days=_DAYS_WINDOW, now=now),
            embedding_model=settings.openai_embedding_model,
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
        by_day=_count_by_day(metadatas, days=_DAYS_WINDOW, now=now),
        embedding_model=settings.openai_embedding_model,
        dimensions=_EMBEDDING_DIMENSIONS,
        as_of=now,
    )


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


def _count_by_day(metadatas: list[dict[str, Any]], *, days: int, now: datetime) -> list[DayCount]:
    """Bucket metadatas by UTC date over the last `days` days, ascending.

    Days with zero entries appear in the response so the UI's bar chart
    has a continuous x-axis. `timestamp_epoch` is the canonical sort key
    (set by `make_metadata` at embed time).
    """
    counter: Counter[str] = Counter()
    cutoff = now - timedelta(days=days)
    cutoff_epoch = cutoff.timestamp()
    for meta in metadatas:
        ts = meta.get("timestamp_epoch")
        if not isinstance(ts, int | float):
            continue
        if ts < cutoff_epoch:
            continue
        date_str = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
        counter[date_str] += 1
    # Emit one row per day in the window so the chart shows the zero days.
    today = now.date()
    series: list[DayCount] = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        date_str = day.strftime("%Y-%m-%d")
        series.append(DayCount(date=date_str, count=counter.get(date_str, 0)))
    return series
