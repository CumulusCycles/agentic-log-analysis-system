"""Unit tests for the claims_service extracted in Phase 6.5 PR 2.

The integration test of behavior is `test_claims_post.py` — these tests exercise
each service function in isolation (no HTTP, no auth middleware) so a failure
points directly at the responsible function.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from shared_data_api.db.models import Claim, ClaimStatusHistory
from shared_data_api.schemas import ClaimCreate
from shared_data_api.services import claims_service


def _jwt(
    user_id: str = "u1",
    app: str = "fnol",
    role: str = "customer",
) -> dict:
    return {"user_id": user_id, "app": app, "role": role}


# ---------------------------------------------------------------------------
# verify_create_authorization
# ---------------------------------------------------------------------------


def test_verify_create_authorization_happy_path():
    claims_service.verify_create_authorization(_jwt(user_id="u1"), "fnol", "u1")
    # No raise — implicit success.


def test_verify_create_authorization_wrong_caller_403():
    with pytest.raises(HTTPException) as exc:
        claims_service.verify_create_authorization(_jwt(), "customer-portal", "u1")
    assert exc.value.status_code == 403
    assert "only fnol" in exc.value.detail.lower()


def test_verify_create_authorization_wrong_jwt_app_403():
    with pytest.raises(HTTPException) as exc:
        claims_service.verify_create_authorization(_jwt(app="customer-portal"), "fnol", "u1")
    assert exc.value.status_code == 403
    assert "not issued for fnol" in exc.value.detail.lower()


def test_verify_create_authorization_wrong_role_403():
    with pytest.raises(HTTPException) as exc:
        claims_service.verify_create_authorization(_jwt(role="agent"), "fnol", "u1")
    assert exc.value.status_code == 403
    assert "customer-role" in exc.value.detail.lower()


def test_verify_create_authorization_user_id_mismatch_403():
    with pytest.raises(HTTPException) as exc:
        claims_service.verify_create_authorization(_jwt(user_id="u1"), "fnol", "different-id")
    assert exc.value.status_code == 403
    assert "another customer" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# load_policy_and_validate
# ---------------------------------------------------------------------------


def _payload(seeded_users, seeded_policy, **overrides) -> ClaimCreate:
    data = {
        "policy_number": seeded_policy["policy_number"],
        "customer_id": seeded_users["customer_id"],
        "vin": seeded_policy["vehicles"][0]["vin"],
        "incident_at": datetime.now(tz=UTC),
        "description": "test claim",
    }
    data.update(overrides)
    return ClaimCreate.model_validate(data)


@pytest.mark.asyncio
async def test_load_policy_and_validate_happy_path(mongo_db, seeded_users, seeded_policy):
    payload = _payload(seeded_users, seeded_policy)
    policy, vehicle = await claims_service.load_policy_and_validate(payload, mongo_db)
    assert policy["policy_number"] == seeded_policy["policy_number"]
    assert vehicle["vin"] == seeded_policy["vehicles"][0]["vin"]


@pytest.mark.asyncio
async def test_load_policy_and_validate_unknown_policy_404(mongo_db, seeded_users, seeded_policy):
    payload = _payload(seeded_users, seeded_policy, policy_number="POL-DOES-NOT-EXIST")
    with pytest.raises(HTTPException) as exc:
        await claims_service.load_policy_and_validate(payload, mongo_db)
    assert exc.value.status_code == 404
    assert "policy not found" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_load_policy_and_validate_wrong_owner_400(mongo_db, seeded_users, seeded_policy):
    payload = _payload(seeded_users, seeded_policy, customer_id="999999999999999999999999")
    with pytest.raises(HTTPException) as exc:
        await claims_service.load_policy_and_validate(payload, mongo_db)
    assert exc.value.status_code == 400
    assert "does not own policy" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_load_policy_and_validate_unknown_vin_400(mongo_db, seeded_users, seeded_policy):
    payload = _payload(seeded_users, seeded_policy, vin="BOGUS_VIN_00000000")
    with pytest.raises(HTTPException) as exc:
        await claims_service.load_policy_and_validate(payload, mongo_db)
    assert exc.value.status_code == 400
    assert "vin not on policy" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# _validate_incident_at  (private helper — tested directly because it carries
# the policy-window + future-skew boundary logic)
# ---------------------------------------------------------------------------


def _policy(effective: datetime, expiration: datetime) -> dict:
    return {"effective_date": effective, "expiration_date": expiration}


def test_validate_incident_at_inside_window_no_raise():
    now = datetime.now(tz=UTC)
    policy = _policy(now - timedelta(days=365), now + timedelta(days=365))
    claims_service._validate_incident_at(now - timedelta(days=1), policy)


def test_validate_incident_at_future_beyond_skew_400():
    now = datetime.now(tz=UTC)
    policy = _policy(now - timedelta(days=365), now + timedelta(days=365))
    with pytest.raises(HTTPException) as exc:
        claims_service._validate_incident_at(now + timedelta(days=1), policy)
    assert exc.value.status_code == 400
    assert "future" in exc.value.detail.lower()


def test_validate_incident_at_before_policy_effective_400():
    now = datetime.now(tz=UTC)
    policy = _policy(now - timedelta(days=30), now + timedelta(days=365))
    with pytest.raises(HTTPException) as exc:
        claims_service._validate_incident_at(now - timedelta(days=365), policy)
    assert exc.value.status_code == 400
    assert "effective" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# persist_new_claim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_new_claim_creates_claim_and_initial_history(
    pg_session_factory, seeded_users, seeded_policy
):
    payload = _payload(seeded_users, seeded_policy)
    vehicle = seeded_policy["vehicles"][0]
    async with pg_session_factory() as session:
        claim = await claims_service.persist_new_claim(
            payload, vehicle, seeded_users["customer_id"], session
        )

    assert claim.current_status == "submitted"
    assert claim.customer_id == seeded_users["customer_id"]
    assert claim.vehicle_snapshot["make"] == vehicle["make"]

    # Verify the initial ClaimStatusHistory row was written in the same transaction.
    async with pg_session_factory() as session:
        history_rows = (
            (
                await session.execute(
                    select(ClaimStatusHistory).where(ClaimStatusHistory.claim_id == claim.id)
                )
            )
            .scalars()
            .all()
        )
    assert len(history_rows) == 1
    h = history_rows[0]
    assert h.from_status is None
    assert h.to_status == "submitted"
    assert h.actor_id == seeded_users["customer_id"]
    # And the persisted Claim row exists.
    async with pg_session_factory() as session:
        persisted = (await session.execute(select(Claim).where(Claim.id == claim.id))).scalar_one()
    assert persisted.policy_number == payload.policy_number
