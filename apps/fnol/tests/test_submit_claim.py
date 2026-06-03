import httpx
import pytest
import respx

VALID_PAYLOAD = {
    "customer_id": "cust-1",
    "policy_number": "POL-1004",
    "vin": "BH0WSDSFF8EJJ7LT4",
    "incident_at": "2026-06-01T10:00:00+00:00",
    "description": "test claim",
}

SDA_RESPONSE = {
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


@pytest.mark.asyncio
async def test_submit_success_passes_through_sda(client, valid_token):
    with respx.mock(base_url="http://shared-data-api-test") as router:
        route = router.post("/claims").mock(return_value=httpx.Response(201, json=SDA_RESPONSE))
        r = await client.post(
            "/fnol/submit",
            json=VALID_PAYLOAD,
            headers={"Authorization": f"Bearer {valid_token}"},
        )

    assert r.status_code == 201
    assert r.json()["id"] == "claim-uuid-1"
    assert route.called


@pytest.mark.asyncio
async def test_submit_forwards_bearer_to_sda(client, valid_token):
    captured = {}

    def _capture(request):
        captured["auth"] = request.headers.get("Authorization")
        captured["x_api_key"] = request.headers.get("X-API-Key")
        return httpx.Response(201, json=SDA_RESPONSE)

    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.post("/claims").mock(side_effect=_capture)
        await client.post(
            "/fnol/submit",
            json=VALID_PAYLOAD,
            headers={"Authorization": f"Bearer {valid_token}"},
        )

    assert captured["auth"] == f"Bearer {valid_token}"
    assert captured["x_api_key"] == "test-fnol-key"


@pytest.mark.asyncio
async def test_submit_missing_bearer_returns_401(client):
    r = await client.post("/fnol/submit", json=VALID_PAYLOAD)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_submit_invalid_bearer_returns_401(client):
    r = await client.post(
        "/fnol/submit",
        json=VALID_PAYLOAD,
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_submit_passes_through_sda_403(client, valid_token):
    """SDA's caller/jwt.app enforcement (only fnol may create claims) — passthrough verbatim."""
    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.post("/claims").mock(
            return_value=httpx.Response(403, json={"detail": "only fnol may create claims"})
        )
        r = await client.post(
            "/fnol/submit",
            json=VALID_PAYLOAD,
            headers={"Authorization": f"Bearer {valid_token}"},
        )

    assert r.status_code == 403
    assert r.json()["detail"] == "only fnol may create claims"


@pytest.mark.asyncio
async def test_submit_sda_unreachable_returns_502(client, valid_token):
    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.post("/claims").mock(side_effect=httpx.ConnectError("dns"))
        r = await client.post(
            "/fnol/submit",
            json=VALID_PAYLOAD,
            headers={"Authorization": f"Bearer {valid_token}"},
        )

    assert r.status_code == 502
