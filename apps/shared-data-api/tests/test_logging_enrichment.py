"""Phase 6.75 — verify each new SDA log event fires with the expected fields.

These tests assert the LOGGING contract (level, event name, fields) for the
enrichment added in this PR. The behavior contracts those events accompany
are covered by `test_auth.py`, `test_claims_post.py`, `test_claims_read.py`,
`test_policies.py`, and `test_simulator.py`.

NEVER assert on credential values — tests confirm credentials are NOT logged.
"""

from datetime import UTC, datetime

import pytest
import structlog
from fastapi import HTTPException

from shared_data_api.schemas import ClaimCreate
from shared_data_api.services import claims_service


def _payload(seeded_users, seeded_policy, **overrides) -> ClaimCreate:
    data = {
        "policy_number": seeded_policy["policy_number"],
        "customer_id": seeded_users["customer_id"],
        "vin": seeded_policy["vehicles"][0]["vin"],
        "incident_at": datetime.now(tz=UTC),
        "description": "test",
    }
    data.update(overrides)
    return ClaimCreate.model_validate(data)


async def _login(client, key):
    resp = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "customer"},
        headers={"X-API-Key": key},
    )
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# auth: login_success / login_failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success_emits_event(client, fnol_key, seeded_users):
    with structlog.testing.capture_logs() as captured:
        resp = await client.post(
            "/auth/login",
            json={"username": "alice", "password": "customer"},
            headers={"X-API-Key": fnol_key},
        )
    assert resp.status_code == 200
    events = [e for e in captured if e.get("event") == "login_success"]
    assert len(events) == 1
    e = events[0]
    assert e["log_level"] == "info"
    assert e["user_id"] == seeded_users["customer_id"]
    assert e["username"] == "alice"
    assert e["role"] == "customer"
    assert e["app"] == "fnol"
    assert e["caller"] == "fnol"
    # CRITICAL: password must not appear in the event payload
    assert "customer" not in str(e.get("password", ""))
    assert "password" not in e


@pytest.mark.asyncio
async def test_login_failed_user_not_found_emits_warn(client, fnol_key, seeded_users):
    with structlog.testing.capture_logs() as captured:
        resp = await client.post(
            "/auth/login",
            json={"username": "does-not-exist", "password": "anything"},
            headers={"X-API-Key": fnol_key},
        )
    assert resp.status_code == 401
    events = [e for e in captured if e.get("event") == "login_failed"]
    assert len(events) == 1
    e = events[0]
    assert e["log_level"] == "warning"
    assert e["reason"] == "user_not_found"
    assert e["username"] == "does-not-exist"
    assert e["caller"] == "fnol"
    assert "password" not in e


@pytest.mark.asyncio
async def test_login_failed_bad_password_emits_warn(client, fnol_key, seeded_users):
    with structlog.testing.capture_logs() as captured:
        resp = await client.post(
            "/auth/login",
            json={"username": "alice", "password": "WRONG"},
            headers={"X-API-Key": fnol_key},
        )
    assert resp.status_code == 401
    events = [e for e in captured if e.get("event") == "login_failed"]
    assert len(events) == 1
    assert events[0]["reason"] == "bad_password"
    assert events[0]["username"] == "alice"
    assert "password" not in events[0]


# ---------------------------------------------------------------------------
# claims_service: claim_created + claim_validation_rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claim_created_emits_info(pg_session_factory, seeded_users, seeded_policy):
    payload = _payload(seeded_users, seeded_policy)
    vehicle = seeded_policy["vehicles"][0]
    with structlog.testing.capture_logs() as captured:
        async with pg_session_factory() as session:
            claim = await claims_service.persist_new_claim(
                payload, vehicle, seeded_users["customer_id"], session
            )
    events = [e for e in captured if e.get("event") == "claim_created"]
    assert len(events) == 1
    e = events[0]
    assert e["log_level"] == "info"
    assert e["claim_id"] == str(claim.id)
    assert e["customer_id"] == seeded_users["customer_id"]
    assert e["policy_number"] == seeded_policy["policy_number"]
    assert e["vin"] == vehicle["vin"]
    assert e["actor_id"] == seeded_users["customer_id"]


@pytest.mark.asyncio
async def test_claim_validation_rejected_vin_not_on_policy(mongo_db, seeded_users, seeded_policy):
    payload = _payload(seeded_users, seeded_policy, vin="BOGUS-VIN-00000")
    with structlog.testing.capture_logs() as captured:
        with pytest.raises(HTTPException):
            await claims_service.load_policy_and_validate(payload, mongo_db)
    events = [e for e in captured if e.get("event") == "claim_validation_rejected"]
    assert len(events) == 1
    e = events[0]
    assert e["log_level"] == "warning"
    assert e["rule"] == "vin_not_on_policy"
    assert e["policy_number"] == seeded_policy["policy_number"]
    assert e["vin"] == "BOGUS-VIN-00000"


def test_claim_validation_rejected_caller_must_be_fnol(seeded_users):
    jwt = {"user_id": seeded_users["customer_id"], "app": "fnol", "role": "customer"}
    with structlog.testing.capture_logs() as captured:
        with pytest.raises(HTTPException):
            claims_service.verify_create_authorization(
                jwt, "customer-portal", seeded_users["customer_id"]
            )
    events = [e for e in captured if e.get("event") == "claim_validation_rejected"]
    assert len(events) == 1
    assert events[0]["rule"] == "caller_must_be_fnol"
    assert events[0]["caller"] == "customer-portal"


# ---------------------------------------------------------------------------
# read paths: policy_fetched / claim_fetched / user_fetched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_policy_fetched_emits_on_list(client, fnol_key, seeded_users, seeded_policy):
    token = await _login(client, fnol_key)
    with structlog.testing.capture_logs() as captured:
        resp = await client.get(
            "/policies",
            params={"customer_id": seeded_users["customer_id"]},
            headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    events = [e for e in captured if e.get("event") == "policy_fetched"]
    assert len(events) == 1
    e = events[0]
    assert e["log_level"] == "info"
    assert e["count"] >= 1
    assert e["customer_id"] == seeded_users["customer_id"]


@pytest.mark.asyncio
async def test_claim_fetched_emits_with_status(client, fnol_key, seeded_users, seeded_policy):
    token = await _login(client, fnol_key)
    payload = _payload(seeded_users, seeded_policy)
    create_resp = await client.post(
        "/claims",
        json={**payload.model_dump(mode="json"), "incident_at": payload.incident_at.isoformat()},
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 201
    claim_id = create_resp.json()["id"]

    with structlog.testing.capture_logs() as captured:
        resp = await client.get(
            f"/claims/{claim_id}",
            headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    events = [e for e in captured if e.get("event") == "claim_fetched"]
    assert len(events) == 1
    assert events[0]["claim_id"] == claim_id
    assert events[0]["current_status"] == "submitted"


@pytest.mark.asyncio
async def test_user_fetched_emits_info(client, fnol_key, seeded_users):
    token = await _login(client, fnol_key)
    with structlog.testing.capture_logs() as captured:
        resp = await client.get(
            f"/users/{seeded_users['customer_id']}",
            headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    events = [e for e in captured if e.get("event") == "user_fetched"]
    assert len(events) == 1
    assert events[0]["user_id"] == seeded_users["customer_id"]
    assert events[0]["role"] == "customer"


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
