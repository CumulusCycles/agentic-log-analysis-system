from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from ..agent.proactive import FindingsBuffer
from ..auth.jwt import get_current_admin
from ..config import Settings, get_settings
from ..ingest.reader import LogReaderError, read_recent_entries
from ..ingest.rollup import HISTORY_WINDOWS, compute_app_status, compute_history_buckets
from ..ingest.spec import APP_LOGS
from ..logging_setup import get_logger
from ..schemas import (
    AppStatus,
    LevelCounts,
    ProactiveFinding,
    StatusHistoryResponse,
    StatusHistoryWindow,
    StatusResponse,
)

router = APIRouter(tags=["status"])
log = get_logger("status")


@router.get("/status", response_model=StatusResponse)
async def get_status(
    request: Request,
    _: dict[str, Any] = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> StatusResponse:
    now = datetime.now(tz=UTC)
    apps: list[AppStatus] = []
    for app_log in APP_LOGS:
        try:
            entries = read_recent_entries(
                app_log, volume_root=settings.log_volume_root, limit=settings.logs_tail_default
            )
        except LogReaderError:
            log.warning(
                "log_volume_unreadable",
                app=app_log.name,
                path=str(app_log.absolute_path(settings.log_volume_root)),
            )
            apps.append(
                AppStatus(
                    name=app_log.name,
                    status="error",
                    file_present=False,
                    last_seen_at=None,
                    counts_1h=LevelCounts(),
                    counts_24h=LevelCounts(),
                    counts_7d=LevelCounts(),
                )
            )
            continue
        apps.append(compute_app_status(app_log.name, entries, now=now, file_present=True))

    # PR 3: corpus_empty drives the Overview "go run the Agitator" banner.
    # Only true when the vectorstore is wired up AND has zero docs — degraded
    # mode (Ollama unreachable) reports False so the banner doesn't dangle.
    findings, last_scan_at, next_scan_at = _proactive_state(
        request, settings.proactive_scan_max_findings
    )
    return StatusResponse(
        as_of=now,
        apps=apps,
        corpus_empty=_corpus_empty(request),
        proactive_findings=findings,
        scan_enabled=settings.proactive_scan_enabled,
        last_scan_at=last_scan_at,
        next_scan_at=next_scan_at,
        # v1.1.2 Option A — lifespan / promotion watchdog write this. Default
        # `"ready"` matches the schema default so older lifespans (or tests
        # that haven't set the attr) report the safer-during-tests value.
        embeddings_state=getattr(request.app.state, "embeddings_state", "ready"),
    )


def _proactive_state(
    request: Request, max_findings: int
) -> tuple[list[ProactiveFinding], datetime | None, datetime | None]:
    """Read the proactive-scan ring buffer + loop timestamps off app.state.

    The buffer is created unconditionally during lifespan (PR 4c), so the
    `is None` branch should never fire in production — kept as a defensive
    guard for tests that build a partially-initialised app.
    """
    buffer: FindingsBuffer | None = getattr(request.app.state, "findings_buffer", None)
    if buffer is None:
        return [], None, None
    return buffer.recent(max_findings), buffer.last_scan_at, buffer.next_scan_at


@router.get("/status/history", response_model=StatusHistoryResponse)
async def get_status_history(
    window: Annotated[
        StatusHistoryWindow,
        Query(description="Window to bucket across. 1h=5min×12; 24h=1h×24; 7d=6h×28."),
    ] = "24h",
    _: dict[str, Any] = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> StatusHistoryResponse:
    """Per-app, per-bucket level counts for the requested window.

    Source is the four mounted log volumes (NOT Chroma — Chroma is
    WARN+ERROR only post-PR-7d ingest gate, but the chart needs INFO too).
    Tail size matches `/api/status` so chart counts stay consistent with the
    1h/24h/7d totals in the same Overview page.
    """
    now = datetime.now(tz=UTC)
    _n_buckets, bucket_minutes = HISTORY_WINDOWS[window]
    apps_history: dict[str, list] = {}
    for app_log in APP_LOGS:
        try:
            entries = read_recent_entries(
                app_log,
                volume_root=settings.log_volume_root,
                limit=settings.logs_tail_default,
            )
        except LogReaderError:
            # Missing/unreadable file → emit empty buckets so the chart still
            # renders with a flat baseline. Same posture as `/api/status`'s
            # error row — surface the gap, don't fail the whole request.
            log.warning(
                "log_volume_unreadable_during_status_history",
                app=app_log.name,
            )
            apps_history[app_log.name] = compute_history_buckets([], now=now, window=window)
            continue
        apps_history[app_log.name] = compute_history_buckets(entries, now=now, window=window)
    return StatusHistoryResponse(
        as_of=now,
        window=window,
        bucket_minutes=bucket_minutes,
        apps=apps_history,
    )


def _corpus_empty(request: Request) -> bool:
    store = getattr(request.app.state, "vectorstore", None)
    if store is None:
        return False
    try:
        count = store._collection.count()  # noqa: SLF001 — Chroma exposes no public count
    except Exception as exc:  # noqa: BLE001 — Chroma transport errors must not crash /api/status
        # Log so the operator can distinguish "empty corpus" from "Chroma
        # unreachable" — without this, both paths return False and the
        # banner stays hidden silently.
        log.warning(
            "corpus_count_failed",
            error_class=type(exc).__name__,
        )
        return False
    return count == 0
