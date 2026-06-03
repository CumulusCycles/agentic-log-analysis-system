from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth.jwt import get_current_user
from ..db import mongo, postgres
from ..db.models import Claim, ClaimStatusHistory
from ..schemas import ClaimCreate, ClaimDetail, ClaimOut

router = APIRouter(tags=["claims"])

# Tolerance for client/server clock skew when checking "incident_at is in the past".
_FUTURE_SKEW = timedelta(minutes=5)


def _as_utc(value: datetime) -> datetime:
    """Normalize a possibly-naive datetime (e.g., from Mongo) to UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _validate_incident_at(incident_at: datetime, policy: dict, now: datetime) -> None:
    incident_at = _as_utc(incident_at)
    if incident_at > now + _FUTURE_SKEW:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="incident_at cannot be in the future",
        )
    effective = _as_utc(policy["effective_date"])
    expiration = _as_utc(policy["expiration_date"])
    if incident_at < effective or incident_at > expiration:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="incident_at outside policy effective window",
        )


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
    return ClaimDetail.model_validate(claim)


@router.post("", response_model=ClaimOut, status_code=status.HTTP_201_CREATED)
async def create_claim(
    payload: ClaimCreate,
    request: Request,
    jwt_payload: dict = Depends(get_current_user),
    session: AsyncSession = Depends(postgres.get_session),
) -> ClaimOut:
    if getattr(request.state, "caller", None) != "fnol":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="only fnol may create claims"
        )
    # Defense in depth: the X-API-Key check above confirms the *caller* is FNOL,
    # but the JWT `app` claim confirms the *user session* was minted for FNOL.
    # Together they prevent reuse of a token issued at CP/AP being replayed
    # through the FNOL API key.
    if jwt_payload.get("app") != "fnol":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="token was not issued for fnol",
        )
    if jwt_payload.get("role") != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only customer-role users may file claims",
        )
    if jwt_payload["user_id"] != payload.customer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="cannot file claims on behalf of another customer",
        )

    db = mongo.get_db()
    policy = await db.policies.find_one({"policy_number": payload.policy_number})
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="policy not found")
    if policy["customer_id"] != payload.customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="customer_id does not own policy",
        )
    vehicle = next((v for v in policy.get("vehicles", []) if v["vin"] == payload.vin), None)
    if vehicle is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="vin not on policy",
        )

    now = datetime.now(tz=UTC)
    _validate_incident_at(payload.incident_at, policy, now)
    claim = Claim(
        policy_number=payload.policy_number,
        customer_id=payload.customer_id,
        vin=payload.vin,
        vehicle_snapshot={
            "make": vehicle["make"],
            "model": vehicle["model"],
            "year": vehicle["year"],
        },
        incident_at=payload.incident_at,
        description=payload.description,
        current_status="submitted",
        created_at=now,
    )
    session.add(claim)
    await session.flush()

    history = ClaimStatusHistory(
        claim_id=claim.id,
        from_status=None,
        to_status="submitted",
        actor_id=jwt_payload["user_id"],
        changed_at=now,
        note="initial submission",
    )
    session.add(history)
    await session.commit()
    await session.refresh(claim)
    return ClaimOut.model_validate(claim)
