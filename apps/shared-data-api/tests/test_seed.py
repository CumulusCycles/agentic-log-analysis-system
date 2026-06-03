import pytest
from sqlalchemy import select

from shared_data_api.config import get_settings
from shared_data_api.db import postgres
from shared_data_api.db.models import Claim, ClaimStatusHistory
from shared_data_api.seeds.seed import run_seed_if_empty

# Per ADR-007, the valid (from, to) transitions are exactly:
VALID_TRANSITIONS: set[tuple[str | None, str]] = {
    (None, "submitted"),
    ("submitted", "triaged"),
    ("triaged", "investigating"),
    ("triaged", "denied"),
    ("investigating", "settled"),
    ("investigating", "denied"),
    ("settled", "closed"),
}

TERMINAL = {"closed", "denied"}


@pytest.mark.asyncio
async def test_seed_produces_only_valid_transitions(mongo_db, pg_session_factory):
    settings = get_settings()
    await run_seed_if_empty(settings)

    async with postgres.session() as s:
        rows = (await s.execute(select(ClaimStatusHistory))).scalars().all()
        assert len(rows) > 0
        for row in rows:
            pair = (row.from_status, row.to_status)
            assert (
                pair in VALID_TRANSITIONS
            ), f"invalid seeded transition {pair} on claim {row.claim_id}"


@pytest.mark.asyncio
async def test_seed_counts_match_spec(mongo_db, pg_session_factory):
    settings = get_settings()
    await run_seed_if_empty(settings)

    customers = await mongo_db.users.count_documents({"role": "customer"})
    agents = await mongo_db.users.count_documents({"role": "agent"})
    policies = await mongo_db.policies.count_documents({})
    assert customers == 10
    assert agents == 5
    assert policies == 15

    async with postgres.session() as s:
        rows = (await s.execute(select(Claim))).scalars().all()
        assert len(rows) == 10


@pytest.mark.asyncio
async def test_seed_is_idempotent(mongo_db, pg_session_factory):
    settings = get_settings()
    await run_seed_if_empty(settings)
    await run_seed_if_empty(settings)  # Second run should be a no-op.

    customers = await mongo_db.users.count_documents({"role": "customer"})
    assert customers == 10  # Not 20.

    async with postgres.session() as s:
        rows = (await s.execute(select(Claim))).scalars().all()
        assert len(rows) == 10  # Not 20.


@pytest.mark.asyncio
async def test_seed_terminal_claims_have_no_invalid_chain(mongo_db, pg_session_factory):
    """Denied chains must traverse triaged (and optionally investigating)."""
    settings = get_settings()
    await run_seed_if_empty(settings)

    async with postgres.session() as s:
        terminal_claims = (
            (await s.execute(select(Claim).where(Claim.current_status.in_(TERMINAL))))
            .scalars()
            .all()
        )
        for claim in terminal_claims:
            history = (
                (
                    await s.execute(
                        select(ClaimStatusHistory)
                        .where(ClaimStatusHistory.claim_id == claim.id)
                        .order_by(ClaimStatusHistory.changed_at)
                    )
                )
                .scalars()
                .all()
            )
            statuses = [h.to_status for h in history]
            assert statuses[0] == "submitted"
            if claim.current_status == "denied":
                assert "triaged" in statuses
                assert statuses[-1] == "denied"
            elif claim.current_status == "closed":
                assert statuses == [
                    "submitted",
                    "triaged",
                    "investigating",
                    "settled",
                    "closed",
                ]
