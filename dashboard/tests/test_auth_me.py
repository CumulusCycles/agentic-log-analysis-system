import jwt


async def test_me_returns_admin_payload_with_valid_token(client, valid_token):
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"username": "admin", "role": "admin"}


async def test_me_missing_token_returns_401(client):
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "missing bearer token"}


async def test_me_invalid_signature_returns_401(client):
    # Sign with a different secret — the dashboard must reject as 401 without
    # leaking which validation step failed.
    forged = jwt.encode(
        {
            "iss": "dashboard",
            "aud": "agentic-log-analysis-dashboard",
            "sub": "admin",
            "role": "admin",
            "iat": 0,
            "exp": 9_999_999_999,
        },
        "wrong-secret",
        algorithm="HS256",
    )
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid token"}
