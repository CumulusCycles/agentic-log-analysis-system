"""pytest for GET /api/status/history.

Covers JWT gating, the window→(n_buckets, bucket_minutes) contract, that
entries land in the bucket containing their timestamp, that out-of-window
entries are ignored, that missing log files emit empty buckets (graceful
degradation), and that invalid window values are rejected.
"""

import json
from datetime import UTC, datetime, timedelta


def _structlog_line(level: str, event: str, ago_sec: int, **fields) -> str:
    ts = datetime.now(tz=UTC) - timedelta(seconds=ago_sec)
    payload = {
        "event": event,
        "level": level,
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        **fields,
    }
    return json.dumps(payload) + "\n"


async def test_status_history_requires_auth(client, log_volume) -> None:
    response = await client.get("/api/status/history")
    assert response.status_code == 401


async def test_status_history_default_window_is_24h(client, valid_token, log_volume) -> None:
    response = await client.get(
        "/api/status/history",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["window"] == "24h"
    assert body["bucket_minutes"] == 60
    assert set(body["apps"].keys()) == {
        "shared-data-api",
        "fnol",
        "customer-portal",
        "agent-portal",
    }
    # 24 buckets per app for the 24h window.
    for buckets in body["apps"].values():
        assert len(buckets) == 24


async def test_status_history_1h_window_has_12_5min_buckets(
    client, valid_token, log_volume
) -> None:
    response = await client.get(
        "/api/status/history?window=1h",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    body = response.json()
    assert body["window"] == "1h"
    assert body["bucket_minutes"] == 5
    for buckets in body["apps"].values():
        assert len(buckets) == 12


async def test_status_history_7d_window_has_28_6h_buckets(client, valid_token, log_volume) -> None:
    response = await client.get(
        "/api/status/history?window=7d",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    body = response.json()
    assert body["window"] == "7d"
    assert body["bucket_minutes"] == 360
    for buckets in body["apps"].values():
        assert len(buckets) == 28


async def test_status_history_buckets_in_chronological_order(
    client, valid_token, log_volume
) -> None:
    """Buckets MUST come back oldest-first so the UI can render
    left-to-right without an extra reverse step."""
    response = await client.get(
        "/api/status/history?window=24h",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    for buckets in response.json()["apps"].values():
        timestamps = [b["ts"] for b in buckets]
        assert timestamps == sorted(timestamps)


async def test_status_history_assigns_recent_entries_to_buckets(
    client, valid_token, log_volume
) -> None:
    """Seed three SDA entries within the last 30 minutes; SDA's total counts
    across all buckets must equal the seeded counts."""
    log_volume["shared-data-api"].write_text(
        _structlog_line("info", "request", 60)
        + _structlog_line("warn", "slow", 180)
        + _structlog_line("error", "boom", 300)
    )
    response = await client.get(
        "/api/status/history?window=1h",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    sda_buckets = response.json()["apps"]["shared-data-api"]
    total_info = sum(b["info"] for b in sda_buckets)
    total_warn = sum(b["warn"] for b in sda_buckets)
    total_error = sum(b["error"] for b in sda_buckets)
    assert total_info == 1
    assert total_warn == 1
    assert total_error == 1


async def test_status_history_ignores_entries_outside_window(
    client, valid_token, log_volume
) -> None:
    """A 1h window must NOT count entries 2h old."""
    log_volume["shared-data-api"].write_text(
        # Within window — counted.
        _structlog_line("error", "recent", 60)
        # Outside window — ignored.
        + _structlog_line("error", "old", 7200)
    )
    response = await client.get(
        "/api/status/history?window=1h",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    sda_buckets = response.json()["apps"]["shared-data-api"]
    total_error = sum(b["error"] for b in sda_buckets)
    assert total_error == 1


async def test_status_history_missing_log_file_returns_empty_buckets(
    client, valid_token, log_volume
) -> None:
    """If a log file is missing, the app gets a full grid of zero buckets —
    the chart still renders with a flat baseline rather than the whole
    request failing."""
    log_volume["fnol"].unlink()
    response = await client.get(
        "/api/status/history?window=24h",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    fnol_buckets = response.json()["apps"]["fnol"]
    assert len(fnol_buckets) == 24
    assert all(b["info"] == 0 and b["warn"] == 0 and b["error"] == 0 for b in fnol_buckets)


async def test_status_history_rejects_invalid_window(client, valid_token, log_volume) -> None:
    response = await client.get(
        "/api/status/history?window=42d",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 422
