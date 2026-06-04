from datetime import UTC, datetime, timedelta

from log_dashboard.ingest.rollup import (
    STATUS_DEGRADED_ERROR_COUNT_1H,
    compute_app_status,
)
from log_dashboard.schemas import LogEntry, LogLevel

_NOW = datetime(2026, 6, 4, 16, 0, 0, tzinfo=UTC)


def _entry(*, seq: int, level: LogLevel, ago_sec: int, app: str = "fnol") -> LogEntry:
    return LogEntry(
        id=f"{app}:{seq}",
        timestamp=_NOW - timedelta(seconds=ago_sec),
        level=level,
        app=app,
        event="x",
        fields={},
        raw="",
    )


def test_status_ok_when_only_info_within_1h() -> None:
    entries = [_entry(seq=i, level=LogLevel.INFO, ago_sec=60) for i in range(5)]
    s = compute_app_status("fnol", entries, now=_NOW, file_present=True)
    assert s.status == "ok"
    assert s.counts_1h.info == 5
    assert s.counts_1h.error == 0


def test_status_degraded_when_error_count_threshold_hit() -> None:
    entries = [
        _entry(seq=i, level=LogLevel.ERROR, ago_sec=60)
        for i in range(STATUS_DEGRADED_ERROR_COUNT_1H)
    ]
    s = compute_app_status("fnol", entries, now=_NOW, file_present=True)
    assert s.status == "degraded"
    assert s.counts_1h.error == STATUS_DEGRADED_ERROR_COUNT_1H


def test_status_degraded_when_error_ratio_threshold_hit_with_meaningful_sample() -> None:
    # 2 errors, 38 infos → 5% ratio, total 40 > 20 sample-size minimum.
    entries = [_entry(seq=i, level=LogLevel.ERROR, ago_sec=30) for i in range(2)] + [
        _entry(seq=i + 10, level=LogLevel.INFO, ago_sec=30) for i in range(38)
    ]
    s = compute_app_status("fnol", entries, now=_NOW, file_present=True)
    assert s.status == "degraded"


def test_status_ok_when_error_ratio_high_but_sample_too_small() -> None:
    # 1 error out of 5 → 20% ratio but only 5 lines, below the 20-sample floor.
    entries = [_entry(seq=0, level=LogLevel.ERROR, ago_sec=30)] + [
        _entry(seq=i + 10, level=LogLevel.INFO, ago_sec=30) for i in range(4)
    ]
    s = compute_app_status("fnol", entries, now=_NOW, file_present=True)
    assert s.status == "ok"


def test_status_error_when_no_recent_entries_within_5_min() -> None:
    # All entries 6 minutes ago — last_seen_at is too old.
    entries = [_entry(seq=i, level=LogLevel.INFO, ago_sec=360) for i in range(3)]
    s = compute_app_status("fnol", entries, now=_NOW, file_present=True)
    assert s.status == "error"


def test_status_error_when_file_missing() -> None:
    s = compute_app_status("fnol", [], now=_NOW, file_present=False)
    assert s.status == "error"
    assert s.last_seen_at is None


def test_window_counts_bucket_correctly_across_1h_24h_7d() -> None:
    entries = [
        _entry(seq=0, level=LogLevel.INFO, ago_sec=30),  # 1h + 24h + 7d
        _entry(seq=1, level=LogLevel.WARN, ago_sec=4_000),  # 24h + 7d only (> 1h)
        _entry(seq=2, level=LogLevel.ERROR, ago_sec=200_000),  # 7d only (> 24h)
        _entry(seq=3, level=LogLevel.INFO, ago_sec=8 * 86_400),  # outside all windows
    ]
    s = compute_app_status("fnol", entries, now=_NOW, file_present=True)
    assert (s.counts_1h.info, s.counts_1h.warn, s.counts_1h.error) == (1, 0, 0)
    assert (s.counts_24h.info, s.counts_24h.warn, s.counts_24h.error) == (1, 1, 0)
    assert (s.counts_7d.info, s.counts_7d.warn, s.counts_7d.error) == (1, 1, 1)
