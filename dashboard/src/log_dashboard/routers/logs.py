from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth.jwt import get_current_admin
from ..config import Settings, get_settings
from ..ingest.reader import LogReaderError, read_recent_entries
from ..ingest.spec import APP_LOGS, APP_NAMES
from ..logging_setup import get_logger
from ..schemas import LogEntry, LogLevel, LogsResponse

router = APIRouter(tags=["logs"])
log = get_logger("logs")


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _validate_apps(raw: list[str]) -> list[str]:
    invalid = [a for a in raw if a not in APP_NAMES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown app(s): {','.join(invalid)}",
        )
    return raw


def _validate_levels(raw: list[str]) -> set[LogLevel]:
    out: set[LogLevel] = set()
    for v in raw:
        try:
            out.add(LogLevel(v.upper()))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown level: {v}",
            ) from exc
    return out


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    app: Annotated[
        str | None,
        Query(description="Comma-separated list of app names. Omit for all."),
    ] = None,
    level: Annotated[
        str | None,
        Query(description="Comma-separated list of levels (INFO,WARN,ERROR,DEBUG)."),
    ] = None,
    before: Annotated[
        datetime | None,
        Query(
            description="Pagination cursor — return entries with timestamp strictly < this value."
        ),
    ] = None,
    since: Annotated[
        datetime | None,
        Query(description="Return entries with timestamp >= this value."),
    ] = None,
    until: Annotated[
        datetime | None,
        Query(
            description=(
                "Upper bound for a custom time window — return entries with timestamp "
                "strictly < this value. AND'd with `before` so pagination and the "
                "time-window filter stay orthogonal."
            ),
        ),
    ] = None,
    limit: Annotated[int | None, Query(ge=1, description="Max entries to return.")] = None,
    _: dict[str, Any] = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> LogsResponse:
    apps_filter = _validate_apps(_parse_csv(app))
    levels_filter = _validate_levels(_parse_csv(level))
    page_size = min(limit or settings.logs_page_default, settings.logs_page_max)
    target_apps = (
        [al for al in APP_LOGS if al.name in apps_filter] if apps_filter else list(APP_LOGS)
    )

    collected: list[LogEntry] = []
    for app_log in target_apps:
        try:
            entries = read_recent_entries(
                app_log,
                volume_root=settings.log_volume_root,
                limit=settings.logs_tail_default,
            )
        except LogReaderError:
            # A missing/unreadable file shouldn't fail the whole request — the
            # status endpoint surfaces that separately. Skip silently here.
            log.warning(
                "log_volume_unreadable_during_logs_query",
                app=app_log.name,
            )
            continue
        for entry in entries:
            if levels_filter and entry.level not in levels_filter:
                continue
            if before is not None and entry.timestamp >= before:
                continue
            if until is not None and entry.timestamp >= until:
                continue
            if since is not None and entry.timestamp < since:
                continue
            collected.append(entry)

    collected.sort(key=lambda e: (e.timestamp, e.app, e.id), reverse=True)
    page = collected[:page_size]
    next_before = page[-1].timestamp if len(collected) > page_size and page else None
    return LogsResponse(entries=page, next_before=next_before)
