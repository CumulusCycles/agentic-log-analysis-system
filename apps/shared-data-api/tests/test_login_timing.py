"""Confirm login timing does not reveal whether a username is valid.

The exact elapsed times depend on the host's bcrypt cost factor — these tests
assert *relative* equivalence (within ~3x) rather than absolute bounds, which
is enough to catch a regression that drops the bcrypt call on the miss branch.
"""

import time

import pytest


@pytest.mark.asyncio
async def test_invalid_user_pays_bcrypt_cost(client, customer_portal_key, seeded_users):
    # Existing user, wrong password.
    t0 = time.perf_counter()
    r1 = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "definitely-not-her-password"},
        headers={"X-API-Key": customer_portal_key},
    )
    valid_user_elapsed = time.perf_counter() - t0

    # Non-existent user.
    t0 = time.perf_counter()
    r2 = await client.post(
        "/auth/login",
        json={"username": "nobody-here", "password": "anything"},
        headers={"X-API-Key": customer_portal_key},
    )
    missing_user_elapsed = time.perf_counter() - t0

    assert r1.status_code == 401
    assert r2.status_code == 401
    # If bcrypt is skipped for missing users, the miss branch would be 10–100x
    # faster than the hit branch. Allow up to 3x to absorb host variance.
    ratio = max(valid_user_elapsed, missing_user_elapsed) / min(
        valid_user_elapsed, missing_user_elapsed
    )
    assert ratio < 3.0, (
        f"login timing differs too much: valid={valid_user_elapsed:.3f}s "
        f"missing={missing_user_elapsed:.3f}s ratio={ratio:.2f}"
    )
