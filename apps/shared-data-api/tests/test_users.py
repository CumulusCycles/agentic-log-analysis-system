"""Negative-case coverage for GET /users/{id}."""

import pytest


async def _login(client, key):
    resp = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "customer"},
        headers={"X-API-Key": key},
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_get_user_returns_self(client, customer_portal_key, seeded_users):
    token = await _login(client, customer_portal_key)
    response = await client.get(
        f"/users/{seeded_users['customer_id']}",
        headers={
            "X-API-Key": customer_portal_key,
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == 200
    assert response.json()["username"] == "alice"


@pytest.mark.asyncio
async def test_get_user_unknown_id_returns_404(client, customer_portal_key, seeded_users):
    token = await _login(client, customer_portal_key)
    # Valid-shape ObjectId that doesn't exist in mongo.
    response = await client.get(
        "/users/000000000000000000000000",
        headers={
            "X-API-Key": customer_portal_key,
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "user not found"


@pytest.mark.asyncio
async def test_get_user_malformed_id_returns_404(client, customer_portal_key, seeded_users):
    """Malformed ids fall through to_object_id and never match — 404, not 500."""
    token = await _login(client, customer_portal_key)
    response = await client.get(
        "/users/not-a-real-id-shape",
        headers={
            "X-API-Key": customer_portal_key,
            "Authorization": f"Bearer {token}",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_user_without_bearer_token_returns_401(client, customer_portal_key, seeded_users):
    response = await client.get(
        f"/users/{seeded_users['customer_id']}",
        headers={"X-API-Key": customer_portal_key},
    )
    assert response.status_code == 401
