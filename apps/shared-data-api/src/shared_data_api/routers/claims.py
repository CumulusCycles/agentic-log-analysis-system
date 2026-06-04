from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth.jwt import get_current_user
from ..db import mongo, postgres
from ..db.models import Claim
from ..logging_setup import get_logger
from ..schemas import ClaimCreate, ClaimDetail, ClaimOut
from ..services import claims_service

router = APIRouter(tags=["claims"])
log = get_logger("claims")


@router.get("", response_model=list[ClaimOut])
async def list_claims(
    customer_id: str | None = None,
    policy_number: str | None = None,
    current_status: str | None = None,
    assigned_adjuster_id: str | None = None,
    _: dict = Depends(get_current_user),
    session: AsyncSession = Depends(postgres.get_session),
) -> list[ClaimOut]:
    stmt = select(Claim)
    if customer_id is not None:
        stmt = stmt.where(Claim.customer_id == customer_id)
    if policy_number is not None:
        stmt = stmt.where(Claim.policy_number == policy_number)
    if current_status is not None:
        stmt = stmt.where(Claim.current_status == current_status)
    if assigned_adjuster_id is not None:
        stmt = stmt.where(Claim.assigned_adjuster_id == assigned_adjuster_id)
    stmt = stmt.order_by(Claim.created_at.desc())
    result = await session.execute(stmt)
    return [ClaimOut.model_validate(c) for c in result.scalars().all()]


@router.get("/{claim_id}", response_model=ClaimDetail)
async def get_claim(
    claim_id: UUID,
    _: dict = Depends(get_current_user),
    session: AsyncSession = Depends(postgres.get_session),
) -> ClaimDetail:
    stmt = select(Claim).where(Claim.id == claim_id).options(selectinload(Claim.history))
    result = await session.execute(stmt)
    claim = result.scalar_one_or_none()
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="claim not found")
    log.info("claim_fetched", claim_id=str(claim.id), current_status=claim.current_status)
    return ClaimDetail.model_validate(claim)


@router.post("", response_model=ClaimOut, status_code=status.HTTP_201_CREATED)
async def create_claim(
    payload: ClaimCreate,
    request: Request,
    jwt_payload: dict = Depends(get_current_user),
    session: AsyncSession = Depends(postgres.get_session),
) -> ClaimOut:
    caller = getattr(request.state, "caller", None)
    claims_service.verify_create_authorization(jwt_payload, caller, payload.customer_id)
    _policy, vehicle = await claims_service.load_policy_and_validate(payload, mongo.get_db())
    claim = await claims_service.persist_new_claim(
        payload, vehicle, jwt_payload["user_id"], session
    )
    return ClaimOut.model_validate(claim)
