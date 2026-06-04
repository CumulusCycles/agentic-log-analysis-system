from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..auth.jwt import encode_token, get_current_user
from ..auth.password import DUMMY_HASH, verify_password
from ..config import Settings, get_settings
from ..db import mongo
from ..db.mongo import to_object_id
from ..logging_setup import get_logger
from ..schemas import LoginRequest, TokenResponse, UserOut

router = APIRouter(tags=["auth"])
log = get_logger("auth")


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    db = mongo.get_db()
    user = await db.users.find_one({"username": payload.username})
    # Always run bcrypt, even when the user does not exist, so the elapsed time
    # of a failed login does not reveal whether the username is valid.
    target_hash = user["password_hash"] if user is not None else DUMMY_HASH
    password_ok = verify_password(payload.password, target_hash)
    caller = getattr(request.state, "caller", None)
    if user is None or not password_ok:
        reason = "user_not_found" if user is None else "bad_password"
        log.warning(
            "login_failed",
            username=payload.username,
            reason=reason,
            caller=caller,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    user_id = str(user["_id"])
    request.state.user_id = user_id

    token = encode_token(
        user_id=user_id,
        role=user["role"],
        app=caller,
        settings=settings,
    )
    log.info(
        "login_success",
        user_id=user_id,
        username=payload.username,
        role=user["role"],
        app=caller,
        caller=caller,
    )
    return TokenResponse(access_token=token, expires_in=settings.jwt_expires_minutes * 60)


@router.get("/me", response_model=UserOut)
async def me(jwt_payload: dict = Depends(get_current_user)) -> UserOut:
    db = mongo.get_db()
    user = await db.users.find_one({"_id": to_object_id(jwt_payload["user_id"])})
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return UserOut(
        id=str(user["_id"]),
        username=user["username"],
        role=user["role"],
        display_name=user["display_name"],
    )
