"""Phase 6.75 — verify FNOL's new log events fire with the expected fields.

NEVER assert on credential values — tests confirm bearer + password are NOT
logged.
"""

import httpx
import pytest
import respx
import structlog

VALID_PAYLOAD = {
    "customer_id": "cust-1",
    "policy_number": "POL-1004",
    "vin": "BH0WSDSFF8EJJ7LT4",
    "incident_at": "2026-06-01T10:00:00+00:00",
    "description": "test claim",
}

SDA_CLAIM_RESPONSE = {
    "id": "claim-uuid-1",
    "policy_number": "POL-1004",
    "customer_id": "cust-1",
    "vin": "BH0WSDSFF8EJJ7LT4",
    "incident_at": "2026-06-01T10:00:00+00:00",
    "description": "test claim",
    "current_status": "submitted",
    "assigned_adjuster_id": None,
    "created_at": "2026-06-03T00:00:00+00:00",
}


# ---------------------------------------------------------------------------
# login_proxied_success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_proxied_success_emits_info(client):
    sda_token = {"access_token": "tok-fake", "token_type": "bearer", "expires_in": 3600}
    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.post("/auth/login").mock(return_value=httpx.Response(200, json=sda_token))
        with structlog.testing.capture_logs() as captured:
            r = await client.post("/auth/login", json={"username": "alice", "password": "customer"})
    assert r.status_code == 200
    events = [e for e in captured if e.get("event") == "login_proxied_success"]
    assert len(events) == 1
    e = events[0]
    assert e["log_level"] == "info"
    assert e["username"] == "alice"
    # CRITICAL: password is NEVER in the event payload
    assert "password" not in e
    assert "customer" not in str(e.get("password", ""))


# ---------------------------------------------------------------------------
# claim_submitted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_submitted_emits_info(client, valid_token):
    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.post("/claims").mock(return_value=httpx.Response(201, json=SDA_CLAIM_RESPONSE))
        with structlog.testing.capture_logs() as captured:
            r = await client.post(
                "/fnol/submit",
                json=VALID_PAYLOAD,
                headers={"Authorization": f"Bearer {valid_token}"},
            )
    assert r.status_code == 201
    events = [e for e in captured if e.get("event") == "claim_submitted"]
    assert len(events) == 1
    e = events[0]
    assert e["log_level"] == "info"
    assert e["claim_id"] == "claim-uuid-1"
    assert e["user_id"] == "test-user-id"
    assert e["policy_number"] == "POL-1004"
    assert e["vin"] == "BH0WSDSFF8EJJ7LT4"
    # CRITICAL: bearer token is NEVER in the event payload
    assert "bearer" not in e
    assert "authorization" not in e
    assert valid_token not in str(e)


# ---------------------------------------------------------------------------
# sda_upstream_rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sda_upstream_rejected_emits_warn(client, valid_token):
    """SDA returns 4xx → FNOL's sda-client emits sda_upstream_rejected (WARN)
    before re-raising; the router translates to HTTPException."""
    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.post("/claims").mock(
            return_value=httpx.Response(403, json={"detail": "only fnol may create claims"})
        )
        with structlog.testing.capture_logs() as captured:
            r = await client.post(
                "/fnol/submit",
                json=VALID_PAYLOAD,
                headers={"Authorization": f"Bearer {valid_token}"},
            )
    assert r.status_code == 403
    events = [e for e in captured if e.get("event") == "sda_upstream_rejected"]
    assert len(events) == 1
    e = events[0]
    assert e["log_level"] == "warning"
    assert e["target"] == "/claims"
    assert e["status"] == 403
    assert e["detail"] == "only fnol may create claims"
    assert valid_token not in str(e)


# ---------------------------------------------------------------------------
# sda_upstream_unreachable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sda_upstream_unreachable_emits_warn(client, valid_token):
    """SDA transport error → FNOL's sda-client emits sda_upstream_unreachable
    (WARN) before re-raising; the router translates to 502."""
    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.post("/claims").mock(side_effect=httpx.ConnectError("dns"))
        with structlog.testing.capture_logs() as captured:
            r = await client.post(
                "/fnol/submit",
                json=VALID_PAYLOAD,
                headers={"Authorization": f"Bearer {valid_token}"},
            )
    assert r.status_code == 502
    events = [e for e in captured if e.get("event") == "sda_upstream_unreachable"]
    assert len(events) == 1
    e = events[0]
    assert e["log_level"] == "warning"
    assert e["target"] == "/claims"
    assert e["error_class"] == "ConnectError"


# ---------------------------------------------------------------------------
# request middleware: X-Source header propagation (ADR-011)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_event_emits_source_from_header(client):
    with structlog.testing.capture_logs() as captured:
        resp = await client.get("/health", headers={"X-Source": "test"})
    assert resp.status_code == 200
    events = [e for e in captured if e.get("event") == "request"]
    assert len(events) == 1
    assert events[0]["source"] == "test"


@pytest.mark.asyncio
async def test_request_event_emits_source_prod_when_header_absent(client):
    with structlog.testing.capture_logs() as captured:
        resp = await client.get("/health")
    assert resp.status_code == 200
    events = [e for e in captured if e.get("event") == "request"]
    assert len(events) == 1
    assert events[0]["source"] == "prod"
