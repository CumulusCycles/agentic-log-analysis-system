"""Auth proxy to SDA.

FNOL holds no passwords and runs no bcrypt. The constant-time guarantee
against user enumeration comes from SDA's `/auth/login` route. FNOL is a
pure pass-through.
"""

import httpx
from fastapi import APIRouter, HTTPException, Request

from ..logging_setup import get_logger
from ..schemas import LoginRequest, TokenResponse

router = APIRouter()
log = get_logger("auth")


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request) -> dict:
    sda = request.app.state.sda
    try:
        result = await sda.login(payload.username, payload.password)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=exc.response.json().get("detail", "login failed"),
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="shared data api unreachable",
        ) from exc
    log.info("login_proxied_success", username=payload.username)
    return result
