"""Per-app status rollup — counts in 1h / 24h / 7d windows + ok/degraded/error.

Thresholds are constants here so they can be tuned without code search. The
status endpoint calls `compute_app_status(entries, now)` once per app.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Literal

from ..schemas import AppStatus, AppStatusKind, LevelCounts, LogLevel, StatusHistoryBucket

# Window → (n_buckets, bucket_minutes). Each window resolves to a small,
# fixed number of buckets so the chart density is consistent regardless of
# the underlying time span.
HISTORY_WINDOWS: dict[str, tuple[int, int]] = {
    "1h": (12, 5),  # 12 × 5-minute buckets = 1 hour
    "24h": (24, 60),  # 24 × 1-hour buckets = 24 hours
    "7d": (28, 360),  # 28 × 6-hour buckets = 7 days
}

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


def compute_history_buckets(
    entries: Iterable,
    *,
    now: datetime,
    window: Literal["1h", "24h", "7d"],
) -> list[StatusHistoryBucket]:
    """Bucket `entries` into the per-window grid for the trend-chart endpoint.

    Returns a list of `StatusHistoryBucket` of length `HISTORY_WINDOWS[window][0]`,
    oldest-first. Buckets are aligned to clean boundaries (UTC epoch modulo
    bucket-size) so identical timestamps on different requests land in the
    same bucket. The rightmost bucket ends one bucket-size in the future of
    `now` — it represents the partial current bucket containing `now`.
    DEBUG entries are ignored, matching `_count_in_window`.
    """
    n_buckets, bucket_minutes = HISTORY_WINDOWS[window]
    bucket_seconds = bucket_minutes * 60
    bucket_size = timedelta(seconds=bucket_seconds)

    # Floor `now` to the nearest bucket boundary, then advance one step so
    # `end` is the exclusive upper bound (one boundary past the bucket that
    # currently contains `now`).
    epoch = int(now.timestamp())
    end_epoch = epoch - (epoch % bucket_seconds) + bucket_seconds
    end = datetime.fromtimestamp(end_epoch, tz=now.tzinfo)
    start = end - n_buckets * bucket_size

    buckets = [
        StatusHistoryBucket(ts=start + i * bucket_size, info=0, warn=0, error=0)
        for i in range(n_buckets)
    ]
    for e in entries:
        if e.timestamp < start or e.timestamp >= end:
            continue
        idx = int((e.timestamp - start).total_seconds() // bucket_seconds)
        # Defensive: the above range check should make this redundant, but a
        # rounding edge at boundary should not crash.
        if idx < 0 or idx >= n_buckets:
            continue
        bucket = buckets[idx]
        if e.level is LogLevel.ERROR:
            bucket.error += 1
        elif e.level is LogLevel.WARN:
            bucket.warn += 1
        elif e.level is LogLevel.INFO:
            bucket.info += 1
    return buckets


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
