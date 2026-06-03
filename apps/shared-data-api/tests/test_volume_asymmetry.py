import uuid
from datetime import UTC, datetime

import pytest
import structlog

from shared_data_api.db import postgres
from shared_data_api.db.consistency import warn_on_volume_asymmetry
from shared_data_api.db.models import Claim, ClaimStatusHistory


async def _add_claim(customer_id: str, adjuster_id: str | None) -> uuid.UUID:
    async with postgres.session() as s:
        claim = Claim(
            id=uuid.uuid4(),
            policy_number="POL-X",
            customer_id=customer_id,
            vin="VIN",
            vehicle_snapshot={},
            incident_at=datetime.now(tz=UTC),
            current_status="triaged",
            assigned_adjuster_id=adjuster_id,
            created_at=datetime.now(tz=UTC),
        )
        s.add(claim)
        await s.flush()
        s.add(
            ClaimStatusHistory(
                claim_id=claim.id,
                from_status="submitted",
                to_status="triaged",
                actor_id=adjuster_id or "system",
                changed_at=datetime.now(tz=UTC),
            )
        )
        await s.commit()
        return claim.id


@pytest.mark.asyncio
async def test_clean_state_emits_no_warning(mongo_db, pg_session_factory, seeded_users):
    await _add_claim(seeded_users["customer_id"], seeded_users["agent_id"])
    with structlog.testing.capture_logs() as captured:
        summary = await warn_on_volume_asymmetry()
    assert summary == {
        "missing_customer_refs": 0,
        "missing_adjuster_refs": 0,
        "missing_actor_refs": 0,
    }
    assert not any(e.get("event") == "volume_asymmetry_detected" for e in captured)
    assert any(e.get("event") == "volume_asymmetry_check_clean" for e in captured)


@pytest.mark.asyncio
async def test_dangling_customer_id_warns(mongo_db, pg_session_factory, seeded_users):
    # Customer id that does not exist in mongo.
    dangling = "000000000000000000000000"
    await _add_claim(dangling, seeded_users["agent_id"])
    with structlog.testing.capture_logs() as captured:
        summary = await warn_on_volume_asymmetry()
    assert summary["missing_customer_refs"] >= 1
    events = [e for e in captured if e.get("event") == "volume_asymmetry_detected"]
    assert len(events) == 1
    assert events[0]["log_level"] == "warning"


@pytest.mark.asyncio
async def test_system_actor_is_not_flagged(mongo_db, pg_session_factory, seeded_users):
    # Simulator's SYSTEM_ACTOR_ID fallback should not trigger an asymmetry alert.
    await _add_claim(seeded_users["customer_id"], None)
    async with postgres.session() as s:
        claim_id = (await s.execute(__import__("sqlalchemy").select(Claim.id))).scalar_one()
        s.add(
            ClaimStatusHistory(
                claim_id=claim_id,
                from_status="triaged",
                to_status="investigating",
                actor_id="system",
                changed_at=datetime.now(tz=UTC),
            )
        )
        await s.commit()
    summary = await warn_on_volume_asymmetry()
    assert summary["missing_actor_refs"] == 0
