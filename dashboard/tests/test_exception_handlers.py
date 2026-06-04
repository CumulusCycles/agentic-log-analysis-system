import structlog

from log_dashboard.routers import auth as auth_router


async def test_unhandled_exception_emits_log_and_returns_500(client, monkeypatch) -> None:
    """Force `verify_password` to raise an uncaught RuntimeError from inside
    the login route, then assert the catch-all handler logs
    `unhandled_exception` and returns the generic 500 body.

    Using an existing route (vs. registering one ad-hoc) avoids the SPA
    catch-all `/{full_path:path}`, which is registered at create_app() time
    and would intercept any later-added test route. Patch the router's
    local binding (`from ..auth.password import verify_password` rebinds at
    module load) rather than the source module.
    """

    def _boom(*_args, **_kwargs) -> bool:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(auth_router, "verify_password", _boom)

    with structlog.testing.capture_logs() as logs:
        response = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "irrelevant"},
        )

    assert response.status_code == 500
    assert response.json() == {"detail": "internal server error"}
    events = [e for e in logs if e.get("event") == "unhandled_exception"]
    assert len(events) == 1
    assert events[0]["error_class"] == "RuntimeError"
    assert events[0]["status"] == 500


async def test_validation_error_emits_log_and_returns_422(client) -> None:
    # POST /api/auth/login with no body → pydantic validation fails.
    with structlog.testing.capture_logs() as logs:
        response = await client.post("/api/auth/login", json={})
    assert response.status_code == 422
    events = [e for e in logs if e.get("event") == "request_validation_error"]
    assert len(events) == 1
    assert events[0]["status"] == 422
