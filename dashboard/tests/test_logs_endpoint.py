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


def _winston_line(level: str, event: str, ago_sec: int) -> str:
    ts = datetime.now(tz=UTC) - timedelta(seconds=ago_sec)
    payload = {
        "level": level,
        "event": event,
        "message": event,
        "service": "customer-portal",
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z",
    }
    return json.dumps(payload) + "\n"


def _logback_line(level: str, event: str, ago_sec: int) -> str:
    ts = datetime.now(tz=UTC) - timedelta(seconds=ago_sec)
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S.") + f"{ts.microsecond // 1000:03d}"
    pad = " " if len(level) == 5 else "  "
    return f"{ts_str} {level}{pad}--- [main] com.foo : {event}\n"


def _seed_mixed(log_volume) -> None:
    log_volume["shared-data-api"].write_text(
        "".join(_structlog_line("info", "request", 600 - i) for i in range(20))
        + _structlog_line("error", "unhandled_exception", 300)
    )
    log_volume["fnol"].write_text(
        "".join(_structlog_line("info", "request", 500 - i) for i in range(10))
        + _structlog_line("warning", "sda_upstream_rejected", 200)
    )
    log_volume["customer-portal"].write_text(
        "".join(_winston_line("info", "request", 400 - i) for i in range(10))
    )
    log_volume["agent-portal"].write_text(
        "".join(_logback_line("INFO", "request", 300 - i) for i in range(10))
        + _logback_line("WARN", "sda_upstream_unreachable", 100)
    )


async def test_logs_requires_auth(client, log_volume) -> None:
    response = await client.get("/api/logs")
    assert response.status_code == 401


async def test_logs_returns_recent_entries_newest_first(client, valid_token, log_volume) -> None:
    _seed_mixed(log_volume)
    response = await client.get(
        "/api/logs?limit=5", headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["entries"]) == 5
    timestamps = [e["timestamp"] for e in body["entries"]]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_logs_filters_by_app(client, valid_token, log_volume) -> None:
    _seed_mixed(log_volume)
    response = await client.get(
        "/api/logs?app=fnol&limit=50",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    body = response.json()
    assert body["entries"]
    assert {e["app"] for e in body["entries"]} == {"fnol"}


async def test_logs_filters_by_level_csv(client, valid_token, log_volume) -> None:
    _seed_mixed(log_volume)
    response = await client.get(
        "/api/logs?level=WARN,ERROR&limit=50",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    body = response.json()
    assert body["entries"]
    assert all(e["level"] in ("WARN", "ERROR") for e in body["entries"])


async def test_logs_pagination_via_next_before(client, valid_token, log_volume) -> None:
    _seed_mixed(log_volume)
    headers = {"Authorization": f"Bearer {valid_token}"}

    page1 = (await client.get("/api/logs?limit=3", headers=headers)).json()
    assert len(page1["entries"]) == 3
    assert page1["next_before"] is not None

    page2 = (
        await client.get(f"/api/logs?limit=3&before={page1['next_before']}", headers=headers)
    ).json()
    # No overlap — every page-2 entry is strictly older than every page-1 entry.
    p1_oldest = page1["entries"][-1]["timestamp"]
    for entry in page2["entries"]:
        assert entry["timestamp"] < p1_oldest


async def test_logs_rejects_unknown_app(client, valid_token, log_volume) -> None:
    response = await client.get(
        "/api/logs?app=ghost",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 422


async def test_logs_caps_limit_at_page_max(client, valid_token, log_volume) -> None:
    _seed_mixed(log_volume)
    # Ask for way more than logs_page_max — server caps silently.
    response = await client.get(
        "/api/logs?limit=99999",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    body = response.json()
    # We have ~42 entries seeded — all should come back, well under the cap.
    assert len(body["entries"]) <= 1000
    assert len(body["entries"]) > 0


# --- PR 2: until query param ---


async def test_logs_until_excludes_entries_at_or_after_cutoff(
    client, valid_token, log_volume
) -> None:
    """`until` is the operator-facing upper bound (entry.timestamp < until)."""
    _seed_mixed(log_volume)
    # The seed's newest entries are at "ago=100s..600s". `until` 250s ago
    # keeps entries older than that and drops the rest.
    until = (datetime.now(tz=UTC) - timedelta(seconds=250)).isoformat()
    response = await client.get(
        "/api/logs",
        params={"until": until, "limit": 200},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    body = response.json()
    cutoff = datetime.fromisoformat(until)
    for entry in body["entries"]:
        ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
        assert ts < cutoff


async def test_logs_since_and_until_window_combined(client, valid_token, log_volume) -> None:
    """`since` + `until` carves out a [since, until) window from the seed."""
    _seed_mixed(log_volume)
    now = datetime.now(tz=UTC)
    since = (now - timedelta(seconds=350)).isoformat()
    until = (now - timedelta(seconds=150)).isoformat()
    response = await client.get(
        "/api/logs",
        params={"since": since, "until": until, "limit": 200},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    body = response.json()
    since_dt = datetime.fromisoformat(since)
    until_dt = datetime.fromisoformat(until)
    assert body["entries"]
    for entry in body["entries"]:
        ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
        assert since_dt <= ts < until_dt


async def test_logs_until_anded_with_before_pagination_cursor(
    client, valid_token, log_volume
) -> None:
    """`until` and `before` are AND'd — the tighter bound wins."""
    _seed_mixed(log_volume)
    now = datetime.now(tz=UTC)
    # `before` = 100s ago (loose upper bound, includes 100s-600s seed)
    # `until` = 400s ago (tight upper bound, only 400s-600s should pass)
    before = (now - timedelta(seconds=100)).isoformat()
    until = (now - timedelta(seconds=400)).isoformat()
    response = await client.get(
        "/api/logs",
        params={"before": before, "until": until, "limit": 200},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    body = response.json()
    cutoff = datetime.fromisoformat(until)
    for entry in body["entries"]:
        ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
        # The tighter `until` wins over the looser `before`.
        assert ts < cutoff
