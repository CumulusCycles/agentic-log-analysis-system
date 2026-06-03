import pytest


@pytest.mark.asyncio
async def test_login_success(client, customer_portal_key, seeded_users):
    response = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "customer"},
        headers={"X-API-Key": customer_portal_key},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_bad_password(client, customer_portal_key, seeded_users):
    response = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "wrong"},
        headers={"X-API-Key": customer_portal_key},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid credentials"


@pytest.mark.asyncio
async def test_login_unknown_user(client, customer_portal_key, seeded_users):
    response = await client.post(
        "/auth/login",
        json={"username": "nobody", "password": "customer"},
        headers={"X-API-Key": customer_portal_key},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_round_trip(client, customer_portal_key, seeded_users):
    login = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "customer"},
        headers={"X-API-Key": customer_portal_key},
    )
    token = login.json()["access_token"]
    me = await client.get(
        "/auth/me",
        headers={
            "X-API-Key": customer_portal_key,
            "Authorization": f"Bearer {token}",
        },
    )
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == "alice"
    assert body["role"] == "customer"


@pytest.mark.asyncio
async def test_me_requires_bearer(client, customer_portal_key, seeded_users):
    response = await client.get("/auth/me", headers={"X-API-Key": customer_portal_key})
    assert response.status_code == 401
