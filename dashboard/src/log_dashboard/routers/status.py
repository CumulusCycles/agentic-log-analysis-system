from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from ..auth.jwt import get_current_admin
from ..config import Settings, get_settings
from ..ingest.reader import LogReaderError, read_recent_entries
from ..ingest.rollup import compute_app_status
from ..ingest.spec import APP_LOGS
from ..logging_setup import get_logger
from ..schemas import AppStatus, LevelCounts, StatusResponse

router = APIRouter(tags=["status"])
log = get_logger("status")


@router.get("/status", response_model=StatusResponse)
async def get_status(
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
    return StatusResponse(as_of=now, apps=apps)
