"""Claim submission and retrieval — both proxy SDA.

`POST /fnol/submit` is the sole write path for claims in the system; SDA
enforces FNOL's exclusivity via `X-API-Key` + `jwt.app == "fnol"`. FNOL
validates the inbound JWT locally so it can short-circuit invalid tokens
without consulting SDA.
"""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from ..auth.jwt import get_current_user
from ..logging_setup import get_logger
from ..schemas import ClaimCreate, ClaimDetail, ClaimOut

router = APIRouter()
log = get_logger("claims")


def _passthrough_http_error(exc: httpx.HTTPStatusError) -> HTTPException:
    try:
        detail = exc.response.json().get("detail", "upstream error")
    except ValueError:
        detail = "upstream error"
    return HTTPException(status_code=exc.response.status_code, detail=detail)


@router.post("/submit", response_model=ClaimOut, status_code=201)
async def submit(
    payload: ClaimCreate, request: Request, claims: dict = Depends(get_current_user)
) -> dict:
    bearer = request.state.bearer
    sda = request.app.state.sda
    try:
        result = await sda.create_claim(payload.model_dump(mode="json"), bearer)
    except httpx.HTTPStatusError as exc:
        raise _passthrough_http_error(exc) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="shared data api unreachable") from exc
    log.info(
        "claim_submitted",
        claim_id=result.get("id"),
        user_id=claims.get("user_id"),
        policy_number=payload.policy_number,
        vin=payload.vin,
    )
    return result


@router.get("/{claim_id}", response_model=ClaimDetail)
async def get_claim(
    claim_id: str, request: Request, _claims: dict = Depends(get_current_user)
) -> dict:
    bearer = request.state.bearer
    sda = request.app.state.sda
    try:
        return await sda.get_claim(claim_id, bearer)
    except httpx.HTTPStatusError as exc:
        raise _passthrough_http_error(exc) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="shared data api unreachable") from exc
