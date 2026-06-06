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


# --- PR 3: corpus_empty flag ---


async def test_status_corpus_empty_false_when_vectorstore_missing(
    client, valid_token, log_volume
) -> None:
    """Embeddings-disabled mode: corpus_empty is False so the UI banner stays hidden."""
    _seed_all_apps_healthy(log_volume)
    response = await client.get("/api/status", headers={"Authorization": f"Bearer {valid_token}"})
    assert response.status_code == 200
    assert response.json()["corpus_empty"] is False


async def test_status_corpus_empty_true_when_vectorstore_empty(
    app_instance, client, valid_token, log_volume, fake_vectorstore
) -> None:
    """Inject an empty fake vectorstore → flag flips to True."""
    _seed_all_apps_healthy(log_volume)
    app_instance.state.vectorstore = fake_vectorstore
    response = await client.get("/api/status", headers={"Authorization": f"Bearer {valid_token}"})
    assert response.status_code == 200
    assert response.json()["corpus_empty"] is True


async def test_status_corpus_empty_false_when_vectorstore_populated(
    app_instance, client, valid_token, log_volume, fake_vectorstore
) -> None:
    """Seed at least one doc → corpus_empty becomes False."""
    from datetime import UTC, datetime

    from log_dashboard.ingest.vectorstore import upsert_entries
    from log_dashboard.schemas import LogEntry, LogLevel

    _seed_all_apps_healthy(log_volume)
    upsert_entries(
        fake_vectorstore,
        [
            LogEntry(
                id="seed:1",
                timestamp=datetime.now(tz=UTC),
                level=LogLevel.INFO,
                app="fnol",
                event="claim_submitted",
                fields={},
                raw="{}",
            )
        ],
    )
    app_instance.state.vectorstore = fake_vectorstore
    response = await client.get("/api/status", headers={"Authorization": f"Bearer {valid_token}"})
    assert response.status_code == 200
    assert response.json()["corpus_empty"] is False


# --- PR 4c: proactive scan findings + loop metadata ---


async def test_status_defaults_to_empty_findings_and_scan_disabled(
    client, valid_token, log_volume
) -> None:
    """Out-of-the-box: scan disabled, no findings, no scan timestamps."""
    _seed_all_apps_healthy(log_volume)
    response = await client.get("/api/status", headers={"Authorization": f"Bearer {valid_token}"})
    body = response.json()
    assert body["proactive_findings"] == []
    assert body["scan_enabled"] is False
    assert body["last_scan_at"] is None
    assert body["next_scan_at"] is None


async def test_status_surfaces_findings_from_buffer_newest_first(
    app_instance, client, valid_token, log_volume
) -> None:
    """Injecting findings into the buffer surfaces them via /api/status,
    newest-first, capped by settings.proactive_scan_max_findings."""
    from datetime import UTC, datetime

    from log_dashboard.schemas import Citation, LogLevel, ProactiveFinding

    _seed_all_apps_healthy(log_volume)
    buffer = app_instance.state.findings_buffer
    cited = Citation(
        id="fnol:abcdef0123456789",
        timestamp=datetime(2026, 6, 6, tzinfo=UTC),
        level=LogLevel.ERROR,
        app="fnol",
        event="chaos_honored",
        raw="status=500",
        score=0.9,
    )
    for i in range(3):
        buffer.append(
            ProactiveFinding(
                id=f"proactive:f{i}",
                scan_started_at=datetime(2026, 6, 6, 12, i, tzinfo=UTC),
                scan_completed_at=datetime(2026, 6, 6, 12, i, 1, tzinfo=UTC),
                summary=f"finding {i}",
                severity="error",
                citations=[cited],
                dry_run=False,
            )
        )
    buffer.last_scan_at = datetime(2026, 6, 6, 12, 3, tzinfo=UTC)
    buffer.next_scan_at = datetime(2026, 6, 6, 12, 18, tzinfo=UTC)

    response = await client.get("/api/status", headers={"Authorization": f"Bearer {valid_token}"})
    body = response.json()
    findings = body["proactive_findings"]
    # Newest-first ordering: f2, f1, f0.
    assert [f["id"] for f in findings] == ["proactive:f2", "proactive:f1", "proactive:f0"]
    assert findings[0]["severity"] == "error"
    assert findings[0]["citations"][0]["id"] == "fnol:abcdef0123456789"
    assert body["last_scan_at"] == "2026-06-06T12:03:00Z"
    assert body["next_scan_at"] == "2026-06-06T12:18:00Z"


async def test_status_caps_findings_at_max_findings_setting(
    app_instance, client, valid_token, log_volume
) -> None:
    """When the buffer holds more than `proactive_scan_max_findings`, only the
    top-N newest are surfaced. Defends against operator surprise when a noisy
    period fills the buffer — UI never shows more than the configured cap."""
    from datetime import UTC, datetime

    from log_dashboard.schemas import ProactiveFinding

    _seed_all_apps_healthy(log_volume)
    buffer = app_instance.state.findings_buffer
    # Settings default for `proactive_scan_max_findings` is 5; inject 8 findings
    # spanning ordered timestamps so we can verify both the cap AND ordering.
    for i in range(8):
        buffer.append(
            ProactiveFinding(
                id=f"proactive:cap{i}",
                scan_started_at=datetime(2026, 6, 6, 13, i, tzinfo=UTC),
                scan_completed_at=datetime(2026, 6, 6, 13, i, 1, tzinfo=UTC),
                summary=f"cap finding {i}",
                severity="info",
                citations=[],
                dry_run=False,
            )
        )

    response = await client.get("/api/status", headers={"Authorization": f"Bearer {valid_token}"})
    findings = response.json()["proactive_findings"]
    # Exactly 5 (default cap), newest-first → cap7, cap6, cap5, cap4, cap3.
    assert len(findings) == 5
    assert [f["id"] for f in findings] == [
        "proactive:cap7",
        "proactive:cap6",
        "proactive:cap5",
        "proactive:cap4",
        "proactive:cap3",
    ]
