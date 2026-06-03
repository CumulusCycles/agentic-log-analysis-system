"""Verify CHECK constraints on the claim status enum.

NOTE: SQLite enforces CHECK constraints when ``foreign_keys`` and
``ignore_check_constraints`` defaults hold (they do here), so these tests
catch enum regressions in the SQLAlchemy schema before they reach Postgres.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from shared_data_api.db import postgres
from shared_data_api.db.models import CLAIM_STATUS_VALUES, Claim, ClaimStatusHistory


def _make_claim(status: str) -> Claim:
    return Claim(
        id=uuid.uuid4(),
        policy_number="POL-X",
        customer_id="cust-1",
        vin="VIN",
        vehicle_snapshot={},
        incident_at=datetime.now(tz=UTC),
        current_status=status,
        created_at=datetime.now(tz=UTC),
    )


def test_enum_values_match_adr007():
    assert set(CLAIM_STATUS_VALUES) == {
        "submitted",
        "triaged",
        "investigating",
        "settled",
        "closed",
        "denied",
    }


@pytest.mark.asyncio
async def test_invalid_claim_status_rejected(pg_session_factory):
    async with postgres.session() as s:
        s.add(_make_claim("bogus"))
        with pytest.raises(IntegrityError):
            await s.commit()


@pytest.mark.asyncio
async def test_valid_claim_status_accepted(pg_session_factory):
    async with postgres.session() as s:
        for value in CLAIM_STATUS_VALUES:
            s.add(_make_claim(value))
        await s.commit()


@pytest.mark.asyncio
async def test_invalid_history_to_status_rejected(pg_session_factory):
    async with postgres.session() as s:
        claim = _make_claim("submitted")
        s.add(claim)
        await s.flush()
        s.add(
            ClaimStatusHistory(
                claim_id=claim.id,
                from_status="submitted",
                to_status="not-a-real-status",
                actor_id="actor-1",
                changed_at=datetime.now(tz=UTC),
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()
