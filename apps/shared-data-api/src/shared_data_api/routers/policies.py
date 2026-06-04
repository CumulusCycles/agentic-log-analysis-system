from fastapi import APIRouter, Depends, HTTPException, status

from ..auth.jwt import get_current_user
from ..db import mongo
from ..logging_setup import get_logger
from ..schemas import PolicyOut, VehicleOut

router = APIRouter(tags=["policies"])
log = get_logger("policies")


def _to_policy_out(doc: dict) -> PolicyOut:
    return PolicyOut(
        policy_number=doc["policy_number"],
        customer_id=doc["customer_id"],
        effective_date=doc["effective_date"],
        expiration_date=doc["expiration_date"],
        coverage_type=doc["coverage_type"],
        premium_cents=doc["premium_cents"],
        vehicles=[VehicleOut(**v) for v in doc.get("vehicles", [])],
    )


@router.get("", response_model=list[PolicyOut])
async def list_policies(
    customer_id: str | None = None,
    _: dict = Depends(get_current_user),
) -> list[PolicyOut]:
    db = mongo.get_db()
    query: dict = {}
    if customer_id is not None:
        query["customer_id"] = customer_id
    cursor = db.policies.find(query)
    docs = await cursor.to_list(length=500)
    log.info("policy_fetched", count=len(docs), customer_id=customer_id)
    return [_to_policy_out(d) for d in docs]


@router.get("/{policy_number}", response_model=PolicyOut)
async def get_policy(policy_number: str, _: dict = Depends(get_current_user)) -> PolicyOut:
    db = mongo.get_db()
    doc = await db.policies.find_one({"policy_number": policy_number})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="policy not found")
    log.info("policy_fetched", policy_number=policy_number, customer_id=doc["customer_id"])
    return _to_policy_out(doc)
