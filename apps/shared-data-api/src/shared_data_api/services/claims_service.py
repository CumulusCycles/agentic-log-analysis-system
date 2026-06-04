"""Business logic for claim creation, extracted from the FNOL `POST /claims` controller.

Service functions raise `HTTPException` directly so the controller stays a thin
pass-through and the global exception handlers (PR 1) still log + structure the
response. The service module knows nothing about FastAPI `Request` — it takes
DTOs, the Mongo db handle, and the SQLAlchemy session as plain arguments.

See ADR-005 for why SDA is the sole writer of claims and why these guardrails
(caller + JWT app + role + user_id) are layered defense-in-depth.
"""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Claim, ClaimStatusHistory
from ..logging_setup import get_logger
from ..schemas import ClaimCreate

log = get_logger("claims_service")

# Tolerance for client/server clock skew when checking "incident_at is in the past".
_FUTURE_SKEW = timedelta(minutes=5)


def _as_utc(value: datetime) -> datetime:
    """Normalize a possibly-naive datetime (e.g., from Mongo) to UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _validate_incident_at(incident_at: datetime, policy: dict) -> None:
    """Reject incident timestamps outside the policy's effective window or in the future."""
    incident_at = _as_utc(incident_at)
    now = datetime.now(tz=UTC)
    policy_number = policy.get("policy_number")
    if incident_at > now + _FUTURE_SKEW:
        log.warning(
            "claim_validation_rejected",
            rule="incident_in_future",
            policy_number=policy_number,
            incident_at=incident_at.isoformat(),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="incident_at cannot be in the future",
        )
    effective = _as_utc(policy["effective_date"])
    expiration = _as_utc(policy["expiration_date"])
    if incident_at < effective or incident_at > expiration:
        log.warning(
            "claim_validation_rejected",
            rule="incident_outside_policy_window",
            policy_number=policy_number,
            incident_at=incident_at.isoformat(),
            effective_date=effective.isoformat(),
            expiration_date=expiration.isoformat(),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="incident_at outside policy effective window",
        )


def verify_create_authorization(
    jwt_payload: dict,
    caller: str | None,
    payload_customer_id: str,
) -> None:
    """Four layered authorization checks for `POST /claims`.

    1. `caller` (from `X-API-Key`) must be "fnol" — only FNOL is the write path.
    2. JWT `app` claim must be "fnol" — defense in depth against cross-app token replay
       (e.g., CP-issued token presented through the FNOL API key).
    3. JWT `role` must be "customer" — agents cannot file claims on customer behalf.
    4. JWT `user_id` must match `payload.customer_id` — no impersonation.
    """
    if caller != "fnol":
        log.warning(
            "claim_validation_rejected",
            rule="caller_must_be_fnol",
            caller=caller,
            payload_customer_id=payload_customer_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only fnol may create claims",
        )
    jwt_app = jwt_payload.get("app")
    if jwt_app != "fnol":
        log.warning(
            "claim_validation_rejected",
            rule="jwt_app_mismatch",
            jwt_app=jwt_app,
            payload_customer_id=payload_customer_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="token was not issued for fnol",
        )
    jwt_role = jwt_payload.get("role")
    if jwt_role != "customer":
        log.warning(
            "claim_validation_rejected",
            rule="role_must_be_customer",
            jwt_role=jwt_role,
            jwt_user_id=jwt_payload.get("user_id"),
            payload_customer_id=payload_customer_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only customer-role users may file claims",
        )
    if jwt_payload["user_id"] != payload_customer_id:
        log.warning(
            "claim_validation_rejected",
            rule="impersonation_blocked",
            jwt_user_id=jwt_payload["user_id"],
            payload_customer_id=payload_customer_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="cannot file claims on behalf of another customer",
        )


async def load_policy_and_validate(
    payload: ClaimCreate,
    db,
) -> tuple[dict, dict]:
    """Load the policy from Mongo, verify ownership + VIN, validate incident_at.

    Returns `(policy, vehicle)` where `vehicle` is the specific entry from the
    policy's vehicles array matching `payload.vin`. Raises:
    - 404 if the policy_number is not found.
    - 400 if the policy is owned by a different customer.
    - 400 if the VIN is not on the policy.
    - 400 from `_validate_incident_at` if the incident timestamp is invalid.
    """
    policy = await db.policies.find_one({"policy_number": payload.policy_number})
    if policy is None:
        log.warning(
            "claim_validation_rejected",
            rule="policy_not_found",
            policy_number=payload.policy_number,
            payload_customer_id=payload.customer_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="policy not found",
        )
    if policy["customer_id"] != payload.customer_id:
        log.warning(
            "claim_validation_rejected",
            rule="customer_does_not_own_policy",
            policy_number=payload.policy_number,
            payload_customer_id=payload.customer_id,
            policy_owner_customer_id=policy["customer_id"],
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="customer_id does not own policy",
        )
    vehicle = next(
        (v for v in policy.get("vehicles", []) if v["vin"] == payload.vin),
        None,
    )
    if vehicle is None:
        log.warning(
            "claim_validation_rejected",
            rule="vin_not_on_policy",
            policy_number=payload.policy_number,
            vin=payload.vin,
            payload_customer_id=payload.customer_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="vin not on policy",
        )
    _validate_incident_at(payload.incident_at, policy)
    return policy, vehicle


async def persist_new_claim(
    payload: ClaimCreate,
    vehicle: dict,
    user_id: str,
    session: AsyncSession,
) -> Claim:
    """Insert a new Claim + initial ClaimStatusHistory row in one transaction.

    Returns the refreshed Claim instance with its server-assigned id and timestamps.
    """
    now = datetime.now(tz=UTC)
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
        actor_id=user_id,
        changed_at=now,
        note="initial submission",
    )
    session.add(history)
    await session.commit()
    await session.refresh(claim)
    log.info(
        "claim_created",
        claim_id=str(claim.id),
        customer_id=payload.customer_id,
        policy_number=payload.policy_number,
        vin=payload.vin,
        actor_id=user_id,
    )
    return claim
