from datetime import UTC, datetime

import pytest


async def _login(client, key):
    resp = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "customer"},
        headers={"X-API-Key": key},
    )
    return resp.json()["access_token"]


async def _create_claim(client, fnol_key, seeded_users, seeded_policy):
    token = await _login(client, fnol_key)
    payload = {
        "policy_number": seeded_policy["policy_number"],
        "customer_id": seeded_users["customer_id"],
        "vin": seeded_policy["vehicles"][0]["vin"],
        "incident_at": datetime.now(tz=UTC).isoformat(),
        "description": "test claim",
    }
    resp = await client.post(
        "/claims",
        json=payload,
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
    )
    return resp.json(), token


@pytest.mark.asyncio
async def test_get_claim_by_id_includes_history(client, fnol_key, seeded_users, seeded_policy):
    created, token = await _create_claim(client, fnol_key, seeded_users, seeded_policy)
    response = await client.get(
        f"/claims/{created['id']}",
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert len(body["history"]) == 1
    assert body["history"][0]["to_status"] == "submitted"


@pytest.mark.asyncio
async def test_list_claims_filter_by_customer(
    client, fnol_key, customer_portal_key, seeded_users, seeded_policy
):
    await _create_claim(client, fnol_key, seeded_users, seeded_policy)

    token = await _login(client, customer_portal_key)
    response = await client.get(
        f"/claims?customer_id={seeded_users['customer_id']}",
        headers={
            "X-API-Key": customer_portal_key,
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1


@pytest.mark.asyncio
async def test_get_claim_404(client, fnol_key, seeded_users):
    token = await _login(client, fnol_key)
    response = await client.get(
        "/claims/00000000-0000-0000-0000-000000000000",
        headers={"X-API-Key": fnol_key, "Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
