"""Verify run_migrations retries transient failures and surfaces the final error.

Opts out of the conftest autouse bypass via @pytest.mark.no_run_migrations_mock
so these tests exercise the real run_migrations() against a mocked
alembic.command.upgrade.
"""

import pytest

from shared_data_api.db import postgres

pytestmark = pytest.mark.no_run_migrations_mock


@pytest.mark.asyncio
async def test_run_migrations_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def flaky_upgrade(cfg, revision):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("transient connection drop")

    monkeypatch.setattr("alembic.command.upgrade", flaky_upgrade)
    await postgres.run_migrations(retries=3, backoff_seconds=0.0)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_run_migrations_gives_up_after_retries(monkeypatch):
    calls = {"n": 0}

    def always_fails(cfg, revision):
        calls["n"] += 1
        raise OSError("persistent failure")

    monkeypatch.setattr("alembic.command.upgrade", always_fails)
    with pytest.raises(OSError, match="persistent failure"):
        await postgres.run_migrations(retries=3, backoff_seconds=0.0)
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_run_migrations_succeeds_first_try(monkeypatch):
    calls = {"n": 0}

    def healthy_upgrade(cfg, revision):
        calls["n"] += 1

    monkeypatch.setattr("alembic.command.upgrade", healthy_upgrade)
    await postgres.run_migrations(retries=2, backoff_seconds=0.0)
    assert calls["n"] == 1
