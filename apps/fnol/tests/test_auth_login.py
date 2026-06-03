import httpx
import pytest
import respx


@pytest.mark.asyncio
async def test_login_success_proxies_token(client):
    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.post("/auth/login").mock(
            return_value=httpx.Response(
                200,
                json={"access_token": "tok-abc", "token_type": "bearer", "expires_in": 3600},
            )
        )
        r = await client.post("/auth/login", json={"username": "alice", "password": "customer"})

    assert r.status_code == 200
    assert r.json()["access_token"] == "tok-abc"


@pytest.mark.asyncio
async def test_login_forwards_sda_x_api_key(client):
    """Every outbound SDA call must carry FNOL's X-API-Key (ADR-006 §1)."""
    captured = {}

    def _capture(request):
        captured["x_api_key"] = request.headers.get("X-API-Key")
        return httpx.Response(
            200, json={"access_token": "x", "token_type": "bearer", "expires_in": 60}
        )

    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.post("/auth/login").mock(side_effect=_capture)
        await client.post("/auth/login", json={"username": "alice", "password": "customer"})

    assert captured["x_api_key"] == "test-fnol-key"


@pytest.mark.asyncio
async def test_login_failure_passes_through_401(client):
    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.post("/auth/login").mock(
            return_value=httpx.Response(401, json={"detail": "invalid credentials"})
        )
        r = await client.post("/auth/login", json={"username": "alice", "password": "WRONG"})

    assert r.status_code == 401
    assert r.json()["detail"] == "invalid credentials"


@pytest.mark.asyncio
async def test_login_sda_unreachable_returns_502(client):
    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.post("/auth/login").mock(side_effect=httpx.ConnectError("boom"))
        r = await client.post("/auth/login", json={"username": "alice", "password": "x"})

    assert r.status_code == 502
    assert "unreachable" in r.json()["detail"]
