import pytest


@pytest.mark.asyncio
async def test_missing_api_key_returns_401(client):
    response = await client.post("/auth/login", json={"username": "x", "password": "y"})
    assert response.status_code == 401
    assert response.json()["detail"] == "missing api key"


@pytest.mark.asyncio
async def test_invalid_api_key_returns_401(client):
    response = await client.post(
        "/auth/login",
        json={"username": "x", "password": "y"},
        headers={"X-API-Key": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid api key"


@pytest.mark.asyncio
async def test_valid_api_key_reaches_handler(client, customer_portal_key, seeded_users):
    response = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "customer"},
        headers={"X-API-Key": customer_portal_key},
    )
    # Reaches handler — credentials are valid so 200; the point is "not 401 from middleware".
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_docs_endpoints_are_anonymous(client):
    # /docs, /openapi.json, and /redoc are intentionally browser-accessible in
    # this local-only stack (ADR-001) — see the api_key middleware for the
    # documented threat-model trade-off.
    for path in ("/docs", "/openapi.json", "/redoc"):
        response = await client.get(path)
        assert response.status_code == 200, f"{path} should be public"


@pytest.mark.asyncio
async def test_openapi_schema_shape(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    body = response.json()
    assert body.get("openapi", "").startswith("3.")
