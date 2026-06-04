import structlog


async def test_login_success_returns_token_and_logs_username_only(client):
    with structlog.testing.capture_logs() as logs:
        response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "hunter2"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 60 * 60
    assert isinstance(body["access_token"], str) and body["access_token"]

    success_events = [e for e in logs if e.get("event") == "login_success"]
    assert len(success_events) == 1
    event = success_events[0]
    assert event["username"] == "admin"
    assert event["role"] == "admin"
    # Credential discipline: the plaintext password MUST NOT appear in any
    # structured field of any log line.
    flattened = " ".join(repr(value) for value in event.values())
    assert "hunter2" not in flattened


async def test_login_bad_password_returns_401_and_logs_reason(client):
    with structlog.testing.capture_logs() as logs:
        response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "WRONG"},
        )
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}

    failed = [e for e in logs if e.get("event") == "login_failed"]
    assert len(failed) == 1
    assert failed[0]["reason"] == "bad_password"
    assert failed[0]["username"] == "admin"
    flattened = " ".join(repr(value) for value in failed[0].values())
    assert "WRONG" not in flattened


async def test_login_unknown_user_returns_401_and_logs_reason(client):
    with structlog.testing.capture_logs() as logs:
        response = await client.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "hunter2"},
        )
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid credentials"}

    failed = [e for e in logs if e.get("event") == "login_failed"]
    assert len(failed) == 1
    assert failed[0]["reason"] == "user_not_found"
    assert failed[0]["username"] == "nobody"


async def test_login_never_logs_admin_password_env_value(client):
    """Defense-in-depth: even on success the bcrypt hash on app.state must
    not leak into logs. Verified by scanning every captured event for any
    hint of the plaintext, the hash, or the secret-key prefix."""
    with structlog.testing.capture_logs() as logs:
        await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "hunter2"},
        )
        await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "WRONG"},
        )
    forbidden = ("hunter2", "$2b$", "test-dashboard-secret")
    for event in logs:
        flat = " ".join(repr(value) for value in event.values())
        for needle in forbidden:
            assert needle not in flat, f"credential leak: {needle!r} in {event!r}"
