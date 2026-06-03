import httpx
import pytest
import respx

CLAIM_DETAIL = {
    "id": "claim-uuid-1",
    "policy_number": "POL-1004",
    "customer_id": "cust-1",
    "vin": "BH0WSDSFF8EJJ7LT4",
    "incident_at": "2026-06-01T10:00:00+00:00",
    "description": "test",
    "current_status": "triaged",
    "assigned_adjuster_id": "agent-1",
    "created_at": "2026-06-03T00:00:00+00:00",
    "history": [
        {
            "from_status": "submitted",
            "to_status": "triaged",
            "actor_id": "system",
            "changed_at": "2026-06-03T00:01:00+00:00",
            "note": None,
        }
    ],
}


@pytest.mark.asyncio
async def test_get_claim_success(client, valid_token):
    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.get("/claims/claim-uuid-1").mock(return_value=httpx.Response(200, json=CLAIM_DETAIL))
        r = await client.get(
            "/fnol/claim-uuid-1", headers={"Authorization": f"Bearer {valid_token}"}
        )

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "claim-uuid-1"
    assert len(body["history"]) == 1


@pytest.mark.asyncio
async def test_get_claim_passes_through_404(client, valid_token):
    with respx.mock(base_url="http://shared-data-api-test") as router:
        router.get("/claims/missing").mock(
            return_value=httpx.Response(404, json={"detail": "claim not found"})
        )
        r = await client.get("/fnol/missing", headers={"Authorization": f"Bearer {valid_token}"})

    assert r.status_code == 404
    assert r.json()["detail"] == "claim not found"


@pytest.mark.asyncio
async def test_get_claim_missing_bearer_returns_401(client):
    r = await client.get("/fnol/anything")
    assert r.status_code == 401
