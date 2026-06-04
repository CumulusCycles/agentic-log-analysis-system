import hmac
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth.jwt import encode_token, get_current_admin
from ..auth.password import DUMMY_HASH, verify_password
from ..config import Settings, get_settings
from ..logging_setup import get_logger
from ..schemas import AdminOut, LoginRequest, TokenResponse

router = APIRouter(tags=["auth"])
log = get_logger("auth")

_ADMIN_ROLE = "admin"


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    expected_username = settings.admin_username
    # Constant-time username compare so the elapsed wall-clock of the field
    # checks doesn't reveal which side mismatched.
    username_ok = hmac.compare_digest(payload.username, expected_username)
    # Always run bcrypt — even on a username miss — so failed-login timing
    # doesn't expose whether the username was valid. The hash to verify
    # against is the real admin hash when the username matches, otherwise the
    # constant-work DUMMY_HASH (matches SDA's pattern in
    # `apps/shared-data-api/src/shared_data_api/routers/auth.py`).
    target_hash = request.app.state.admin_password_hash if username_ok else DUMMY_HASH
    password_ok = verify_password(payload.password, target_hash)

    if not (username_ok and password_ok):
        reason = "user_not_found" if not username_ok else "bad_password"
        log.warning(
            "login_failed",
            username=payload.username,
            reason=reason,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    token = encode_token(
        username=expected_username,
        role=_ADMIN_ROLE,
        settings=settings,
    )
    log.info(
        "login_success",
        username=expected_username,
        role=_ADMIN_ROLE,
    )
    return TokenResponse(access_token=token, expires_in=settings.jwt_expires_minutes * 60)


@router.get("/me", response_model=AdminOut)
async def me(jwt_payload: dict[str, Any] = Depends(get_current_admin)) -> AdminOut:
    return AdminOut(
        username=jwt_payload.get("sub", ""),
        role=jwt_payload.get("role", ""),
    )
