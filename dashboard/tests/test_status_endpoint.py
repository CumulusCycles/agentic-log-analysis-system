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


def _winston_line(level: str, event: str, ago_sec: int, **fields) -> str:
    ts = datetime.now(tz=UTC) - timedelta(seconds=ago_sec)
    payload = {
        "level": level,
        "event": event,
        "message": event,
        "service": "customer-portal",
        "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z",
        **fields,
    }
    return json.dumps(payload) + "\n"


def _logback_line(level: str, event: str, ago_sec: int, kv: str = "") -> str:
    ts = datetime.now(tz=UTC) - timedelta(seconds=ago_sec)
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S.") + f"{ts.microsecond // 1000:03d}"
    pad = " " if len(level) == 5 else "  "
    return f"{ts_str} {level}{pad}--- [main] com.foo : {event} {kv}\n"


def _seed_all_apps_healthy(log_volume) -> None:
    log_volume["shared-data-api"].write_text(
        "".join(_structlog_line("info", "request", i) for i in range(5))
    )
    log_volume["fnol"].write_text("".join(_structlog_line("info", "request", i) for i in range(5)))
    log_volume["customer-portal"].write_text(
        "".join(_winston_line("info", "request", i) for i in range(5))
    )
    log_volume["agent-portal"].write_text(
        "".join(_logback_line("INFO", "request", i) for i in range(5))
    )


async def test_status_requires_auth(client, log_volume) -> None:
    response = await client.get("/api/status")
    assert response.status_code == 401


async def test_status_returns_all_four_apps_ok(client, valid_token, log_volume) -> None:
    _seed_all_apps_healthy(log_volume)
    response = await client.get("/api/status", headers={"Authorization": f"Bearer {valid_token}"})
    assert response.status_code == 200
    body = response.json()
    names = [a["name"] for a in body["apps"]]
    assert names == [
        "shared-data-api",
        "fnol",
        "customer-portal",
        "agent-portal",
    ]
    assert all(a["status"] == "ok" for a in body["apps"])
    assert all(a["file_present"] for a in body["apps"])


async def test_status_reports_error_for_missing_log_file(client, valid_token, log_volume) -> None:
    _seed_all_apps_healthy(log_volume)
    # Remove FNOL's log file → file_present should flip to False, status=error.
    log_volume["fnol"].unlink()
    response = await client.get("/api/status", headers={"Authorization": f"Bearer {valid_token}"})
    body = response.json()
    fnol_row = next(a for a in body["apps"] if a["name"] == "fnol")
    assert fnol_row["status"] == "error"
    assert fnol_row["file_present"] is False
    # Others remain ok.
    sda_row = next(a for a in body["apps"] if a["name"] == "shared-data-api")
    assert sda_row["status"] == "ok"


async def test_status_reports_degraded_on_recent_error_burst(
    client, valid_token, log_volume
) -> None:
    _seed_all_apps_healthy(log_volume)
    # Append 10 ERROR lines in the last minute → triggers count threshold.
    log_volume["shared-data-api"].write_text(
        log_volume["shared-data-api"].read_text()
        + "".join(_structlog_line("error", "unhandled_exception", 30) for _ in range(10))
    )
    response = await client.get("/api/status", headers={"Authorization": f"Bearer {valid_token}"})
    sda_row = next(a for a in response.json()["apps"] if a["name"] == "shared-data-api")
    assert sda_row["status"] == "degraded"
    assert sda_row["counts_1h"]["error"] >= 10
