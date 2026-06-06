from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Request

from ..agent.proactive import FindingsBuffer
from ..auth.jwt import get_current_admin
from ..config import Settings, get_settings
from ..ingest.reader import LogReaderError, read_recent_entries
from ..ingest.rollup import compute_app_status
from ..ingest.spec import APP_LOGS
from ..logging_setup import get_logger
from ..schemas import AppStatus, LevelCounts, ProactiveFinding, StatusResponse

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
    # mode (no OpenAI key) reports False so the banner doesn't dangle.
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
