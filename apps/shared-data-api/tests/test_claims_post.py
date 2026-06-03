from datetime import UTC, datetime

import pytest


async def _login(client, key):
    resp = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "customer"},
        headers={"X-API-Key": key},
    )
    return resp.json()["access_token"]


def _payload(seeded_users, seeded_policy):
    return {
        "policy_number": seeded_policy["policy_number"],
        "customer_id": seeded_users["customer_id"],
        "vin": seeded_policy["vehicles"][0]["vin"],
        "incident_at": datetime.now(tz=UTC).isoformat(),
        "description": "rear-ended at light",
    }


@pytest.mark.asyncio
async def test_post_claim_with_fnol_key_creates(client, fnol_key, seeded_users, seeded_policy):
    token = await _login(client, fnol_key)
    response = await client.post(
        "/claims",
        json=_payload(seeded_users, seeded_policy),
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["current_status"] == "submitted"
    assert body["vehicle_snapshot"]["make"] == "Honda"


@pytest.mark.asyncio
async def test_post_claim_with_cp_key_is_forbidden(
    client, customer_portal_key, seeded_users, seeded_policy
):
    token = await _login(client, customer_portal_key)
    response = await client.post(
        "/claims",
        json=_payload(seeded_users, seeded_policy),
        headers={
            "X-API-Key": customer_portal_key,
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == 403
    assert "fnol" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_claim_with_ap_key_is_forbidden(
    client, agent_portal_key, fnol_key, seeded_users, seeded_policy
):
    # Login under fnol so a valid token exists, then try POST with AP key.
    token = await _login(client, fnol_key)
    response = await client.post(
        "/claims",
        json=_payload(seeded_users, seeded_policy),
        headers={
            "X-API-Key": agent_portal_key,
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_post_claim_for_other_customer_forbidden(
    client, fnol_key, seeded_users, seeded_policy
):
    # Login as alice but try to file a claim under a different customer_id.
    token = await _login(client, fnol_key)
    payload = _payload(seeded_users, seeded_policy)
    payload["customer_id"] = "999999999999999999999999"
    response = await client.post(
        "/claims",
        json=payload,
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "another customer" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_claim_agent_role_forbidden(client, fnol_key, seeded_users, seeded_policy):
    # Agent logs in via the fnol api key and tries to file a claim.
    login = await client.post(
        "/auth/login",
        json={"username": "agent1", "password": "agent"},
        headers={"X-API-Key": fnol_key},
    )
    token = login.json()["access_token"]
    payload = _payload(seeded_users, seeded_policy)
    response = await client.post(
        "/claims",
        json=payload,
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert "customer-role" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_claim_with_cp_issued_token_via_fnol_key_forbidden(
    client, fnol_key, customer_portal_key, seeded_users, seeded_policy
):
    """Cross-app token replay: a CP-issued JWT presented through the FNOL API key
    must be rejected even though both the API key and JWT are individually valid."""
    # Mint a token from the customer-portal login flow (JWT.app=customer-portal).
    login = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "customer"},
        headers={"X-API-Key": customer_portal_key},
    )
    cp_token = login.json()["access_token"]

    # Now present that token through the fnol API key (impersonation attempt).
    response = await client.post(
        "/claims",
        json=_payload(seeded_users, seeded_policy),
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {cp_token}"},
    )
    assert response.status_code == 403
    assert "not issued for fnol" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_claim_unknown_vin(client, fnol_key, seeded_users, seeded_policy):
    token = await _login(client, fnol_key)
    payload = _payload(seeded_users, seeded_policy)
    payload["vin"] = "BOGUS_VIN_00000000"
    response = await client.post(
        "/claims",
        json=payload,
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_post_claim_future_incident_rejected(client, fnol_key, seeded_users, seeded_policy):
    from datetime import timedelta

    token = await _login(client, fnol_key)
    payload = _payload(seeded_users, seeded_policy)
    future = datetime.now(tz=UTC) + timedelta(days=1)
    payload["incident_at"] = future.isoformat()
    response = await client.post(
        "/claims",
        json=payload,
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "future" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_claim_before_policy_effective_rejected(
    client, fnol_key, seeded_users, seeded_policy
):
    token = await _login(client, fnol_key)
    payload = _payload(seeded_users, seeded_policy)
    # Seeded_policy effective from 2020 — push incident to 2019.
    payload["incident_at"] = "2019-06-01T12:00:00+00:00"
    response = await client.post(
        "/claims",
        json=payload,
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "effective" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_claim_after_policy_expiration_rejected(
    client, fnol_key, mongo_db, seeded_users
):
    # Custom policy that expired well before "now" so the incident date can be
    # after expiration without also tripping the future-date check.
    from datetime import datetime

    expired_policy = {
        "policy_number": "POL-EXPIRED",
        "customer_id": seeded_users["customer_id"],
        "effective_date": datetime(2018, 1, 1),
        "expiration_date": datetime(2019, 1, 1),
        "coverage_type": "auto-comprehensive",
        "premium_cents": 100_000,
        "vehicles": [{"vin": "VINEXPIRED1234567", "make": "Honda", "model": "Civic", "year": 2018}],
    }
    await mongo_db.policies.insert_one(expired_policy)

    token = await _login(client, fnol_key)
    payload = {
        "policy_number": "POL-EXPIRED",
        "customer_id": seeded_users["customer_id"],
        "vin": "VINEXPIRED1234567",
        # 2020 is after the policy expired (2019) but well before "now" (2026).
        "incident_at": "2020-06-15T12:00:00+00:00",
        "description": "fender bender",
    }
    response = await client.post(
        "/claims",
        json=payload,
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "effective" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_claim_at_clock_skew_boundary_accepted(
    client, fnol_key, seeded_users, seeded_policy
):
    """A 2-minute future timestamp falls inside the 5-minute clock-skew tolerance."""
    from datetime import timedelta

    token = await _login(client, fnol_key)
    payload = _payload(seeded_users, seeded_policy)
    near_future = datetime.now(tz=UTC) + timedelta(minutes=2)
    payload["incident_at"] = near_future.isoformat()
    response = await client.post(
        "/claims",
        json=payload,
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
