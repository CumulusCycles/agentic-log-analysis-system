import random
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select

from shared_data_api.config import get_settings
from shared_data_api.db import postgres
from shared_data_api.db.models import Claim, ClaimStatusHistory
from shared_data_api.simulator.claim_status import (
    TERMINAL,
    TRANSITIONS,
    ClaimStatusSimulator,
    pick_next_status,
)


@pytest.mark.asyncio
async def test_tick_advances_submitted_claim(mongo_db, pg_session_factory, seeded_users):
    """Force the next-status decision via patching so the assertion doesn't
    depend on the specific output of any particular Random(seed)."""
    async with postgres.session() as s:
        claim = Claim(
            id=uuid.uuid4(),
            policy_number="POL-9001",
            customer_id=seeded_users["customer_id"],
            vin="VIN12345678901234",
            vehicle_snapshot={"make": "Honda", "model": "Civic", "year": 2022},
            incident_at=datetime.now(tz=UTC),
            current_status="submitted",
            created_at=datetime.now(tz=UTC),
        )
        s.add(claim)
        await s.commit()
        claim_id = claim.id

    settings = get_settings()
    sim = ClaimStatusSimulator(settings, rng=random.Random())
    with patch(
        "shared_data_api.simulator.claim_status.pick_next_status",
        return_value="triaged",
    ):
        new_status = await sim.tick()

    assert new_status == "triaged"
    async with postgres.session() as s:
        refreshed = (await s.execute(select(Claim).where(Claim.id == claim_id))).scalar_one()
        assert refreshed.current_status == "triaged"
        # Only one agent in seeded_users, so rng.choice is deterministic without
        # depending on the rng's seed.
        assert refreshed.assigned_adjuster_id == seeded_users["agent_id"]

        history = (
            (
                await s.execute(
                    select(ClaimStatusHistory).where(ClaimStatusHistory.claim_id == claim_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(history) == 1
        assert history[0].from_status == "submitted"
        assert history[0].to_status == "triaged"
        assert history[0].actor_id == seeded_users["agent_id"]


@pytest.mark.asyncio
async def test_tick_no_change_when_picker_returns_none(mongo_db, pg_session_factory, seeded_users):
    """If pick_next_status returns None (the 'stay' outcome), the claim is unchanged."""
    async with postgres.session() as s:
        claim = Claim(
            id=uuid.uuid4(),
            policy_number="POL-9001",
            customer_id=seeded_users["customer_id"],
            vin="VIN",
            vehicle_snapshot={},
            incident_at=datetime.now(tz=UTC),
            current_status="triaged",
            assigned_adjuster_id=seeded_users["agent_id"],
            created_at=datetime.now(tz=UTC),
        )
        s.add(claim)
        await s.commit()
        claim_id = claim.id

    settings = get_settings()
    sim = ClaimStatusSimulator(settings, rng=random.Random())
    with patch(
        "shared_data_api.simulator.claim_status.pick_next_status",
        return_value=None,
    ):
        result = await sim.tick()

    assert result is None
    async with postgres.session() as s:
        refreshed = (await s.execute(select(Claim).where(Claim.id == claim_id))).scalar_one()
        assert refreshed.current_status == "triaged"
        history = (
            (
                await s.execute(
                    select(ClaimStatusHistory).where(ClaimStatusHistory.claim_id == claim_id)
                )
            )
            .scalars()
            .all()
        )
        assert history == []


@pytest.mark.asyncio
async def test_tick_records_terminal_transition(mongo_db, pg_session_factory, seeded_users):
    """Forced denied transition writes history correctly and moves claim to terminal."""
    async with postgres.session() as s:
        claim = Claim(
            id=uuid.uuid4(),
            policy_number="POL-9001",
            customer_id=seeded_users["customer_id"],
            vin="VIN",
            vehicle_snapshot={},
            incident_at=datetime.now(tz=UTC),
            current_status="triaged",
            assigned_adjuster_id=seeded_users["agent_id"],
            created_at=datetime.now(tz=UTC),
        )
        s.add(claim)
        await s.commit()
        claim_id = claim.id

    settings = get_settings()
    sim = ClaimStatusSimulator(settings, rng=random.Random())
    with patch(
        "shared_data_api.simulator.claim_status.pick_next_status",
        return_value="denied",
    ):
        result = await sim.tick()

    assert result == "denied"
    async with postgres.session() as s:
        refreshed = (await s.execute(select(Claim).where(Claim.id == claim_id))).scalar_one()
        assert refreshed.current_status == "denied"
        history = (
            (
                await s.execute(
                    select(ClaimStatusHistory).where(ClaimStatusHistory.claim_id == claim_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(history) == 1
        assert history[0].from_status == "triaged"
        assert history[0].to_status == "denied"
        assert history[0].actor_id == seeded_users["agent_id"]


@pytest.mark.asyncio
async def test_tick_with_no_claims_returns_none(mongo_db, pg_session_factory, seeded_users):
    settings = get_settings()
    sim = ClaimStatusSimulator(settings, rng=random.Random(0))
    assert await sim.tick() is None


@pytest.mark.asyncio
async def test_tick_skips_terminal_claims(mongo_db, pg_session_factory, seeded_users):
    async with postgres.session() as s:
        for status_value in ("closed", "denied"):
            s.add(
                Claim(
                    id=uuid.uuid4(),
                    policy_number="POL-9001",
                    customer_id=seeded_users["customer_id"],
                    vin="VIN",
                    vehicle_snapshot={},
                    incident_at=datetime.now(tz=UTC),
                    current_status=status_value,
                    created_at=datetime.now(tz=UTC),
                )
            )
        await s.commit()

    settings = get_settings()
    sim = ClaimStatusSimulator(settings, rng=random.Random(0))
    assert await sim.tick() is None


def test_transition_table_covers_all_non_terminal_statuses():
    non_terminal = {"submitted", "triaged", "investigating", "settled"}
    assert set(TRANSITIONS.keys()) == non_terminal
    assert TERMINAL == frozenset({"closed", "denied"})


def test_pick_next_status_distribution_unbiased_for_triaged():
    """With independent weights, denied should fire ~10%, investigating ~70%, stay ~20%.

    Old sequential-rolls logic gave denied only ~3% because investigating's 70%
    roll consumed most of the probability space first.
    """
    rng = random.Random(123)
    counts = {"investigating": 0, "denied": 0, None: 0}
    n = 20_000
    for _ in range(n):
        counts[pick_next_status("triaged", rng)] += 1
    inv_pct = counts["investigating"] / n
    denied_pct = counts["denied"] / n
    stay_pct = counts[None] / n
    assert 0.67 <= inv_pct <= 0.73, f"investigating={inv_pct:.3f}"
    assert 0.08 <= denied_pct <= 0.12, f"denied={denied_pct:.3f}"
    assert 0.17 <= stay_pct <= 0.23, f"stay={stay_pct:.3f}"


def test_pick_next_status_returns_none_for_terminal():
    rng = random.Random(0)
    assert pick_next_status("closed", rng) is None
    assert pick_next_status("denied", rng) is None


def test_pick_next_status_only_returns_valid_targets():
    rng = random.Random(7)
    for source, choices in TRANSITIONS.items():
        valid_targets = {target for target, _ in choices} | {None}
        for _ in range(200):
            assert pick_next_status(source, rng) in valid_targets
