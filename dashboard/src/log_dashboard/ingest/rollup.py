"""Per-app status rollup — counts in 1h / 24h / 7d windows + ok/degraded/error.

Thresholds are constants here so they can be tuned without code search. The
status endpoint calls `compute_app_status(entries, now)` once per app.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

from ..schemas import AppStatus, AppStatusKind, LevelCounts, LogLevel

STATUS_STALENESS_THRESHOLD_SEC = 300  # 5 min
STATUS_DEGRADED_ERROR_COUNT_1H = 10
STATUS_DEGRADED_ERROR_RATIO_1H = 0.05
STATUS_DEGRADED_RATIO_MIN_TOTAL_1H = 20  # ratio rule only fires when sample size is meaningful


def _count_in_window(entries: list, *, now: datetime, window_sec: int) -> LevelCounts:
    cutoff = now - timedelta(seconds=window_sec)
    counts = LevelCounts()
    for e in entries:
        if e.timestamp < cutoff:
            continue
        if e.level is LogLevel.ERROR:
            counts.error += 1
        elif e.level is LogLevel.WARN:
            counts.warn += 1
        elif e.level is LogLevel.INFO:
            counts.info += 1
        # DEBUG is intentionally not counted in the status rollup
    return counts


def _classify(
    *, file_present: bool, last_seen_at: datetime | None, counts_1h: LevelCounts, now: datetime
) -> AppStatusKind:
    if not file_present:
        return "error"
    if last_seen_at is None:
        return "error"
    if (now - last_seen_at).total_seconds() > STATUS_STALENESS_THRESHOLD_SEC:
        return "error"
    if counts_1h.error >= STATUS_DEGRADED_ERROR_COUNT_1H:
        return "degraded"
    total_1h = counts_1h.info + counts_1h.warn + counts_1h.error
    if (
        total_1h >= STATUS_DEGRADED_RATIO_MIN_TOTAL_1H
        and counts_1h.error / total_1h >= STATUS_DEGRADED_ERROR_RATIO_1H
    ):
        return "degraded"
    return "ok"


def compute_app_status(
    name: str,
    entries: Iterable,
    *,
    now: datetime,
    file_present: bool,
) -> AppStatus:
    """Roll a tail of entries up into the per-app status card."""
    entries_list = list(entries)
    last_seen_at = max((e.timestamp for e in entries_list), default=None)
    counts_1h = _count_in_window(entries_list, now=now, window_sec=3600)
    counts_24h = _count_in_window(entries_list, now=now, window_sec=86_400)
    counts_7d = _count_in_window(entries_list, now=now, window_sec=7 * 86_400)
    status = _classify(
        file_present=file_present, last_seen_at=last_seen_at, counts_1h=counts_1h, now=now
    )
    return AppStatus(
        name=name,
        status=status,
        file_present=file_present,
        last_seen_at=last_seen_at,
        counts_1h=counts_1h,
        counts_24h=counts_24h,
        counts_7d=counts_7d,
    )
