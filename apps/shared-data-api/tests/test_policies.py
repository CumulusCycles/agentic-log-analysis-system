import pytest


async def _login(client, key):
    resp = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "customer"},
        headers={"X-API-Key": key},
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_get_policy_by_number(client, customer_portal_key, seeded_users, seeded_policy):
    token = await _login(client, customer_portal_key)
    response = await client.get(
        "/policies/POL-9001",
        headers={
            "X-API-Key": customer_portal_key,
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["policy_number"] == "POL-9001"
    assert len(body["vehicles"]) == 1


@pytest.mark.asyncio
async def test_get_policy_404(client, customer_portal_key, seeded_users):
    token = await _login(client, customer_portal_key)
    response = await client.get(
        "/policies/POL-NONE",
        headers={
            "X-API-Key": customer_portal_key,
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_policies_by_customer(client, customer_portal_key, seeded_users, seeded_policy):
    token = await _login(client, customer_portal_key)
    response = await client.get(
        f"/policies?customer_id={seeded_users['customer_id']}",
        headers={
            "X-API-Key": customer_portal_key,
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["policy_number"] == "POL-9001"


@pytest.mark.asyncio
async def test_list_policies_with_no_filter_returns_all(
    client, customer_portal_key, mongo_db, seeded_users, seeded_policy
):
    """Without ``customer_id``, the endpoint returns every policy."""
    from datetime import datetime

    await mongo_db.policies.insert_one(
        {
            "policy_number": "POL-9002",
            "customer_id": seeded_users["customer_id"],
            "effective_date": datetime(2020, 1, 1),
            "expiration_date": datetime(2030, 1, 1),
            "coverage_type": "auto-liability",
            "premium_cents": 80_000,
            "vehicles": [
                {"vin": "VIN98765432109876", "make": "Toyota", "model": "Camry", "year": 2021}
            ],
        }
    )

    token = await _login(client, customer_portal_key)
    response = await client.get(
        "/policies",
        headers={
            "X-API-Key": customer_portal_key,
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == 200
    body = response.json()
    policy_numbers = {p["policy_number"] for p in body}
    assert policy_numbers >= {"POL-9001", "POL-9002"}
