"""Verify create_all retries transient failures and surfaces the final error."""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from shared_data_api.db import postgres


@pytest.mark.asyncio
async def test_create_all_retries_then_succeeds(monkeypatch):
    """First call to Base.metadata.create_all raises, second succeeds."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    postgres._engine = engine

    calls = {"n": 0}

    from shared_data_api.db.models import Base

    original_create_all = Base.metadata.create_all

    def flaky_create_all(bind, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("transient connection drop")
        return original_create_all(bind, *args, **kwargs)

    monkeypatch.setattr(Base.metadata, "create_all", flaky_create_all)
    try:
        await postgres.create_all(retries=3, backoff_seconds=0.0)
        assert calls["n"] == 2  # one fail + one success
    finally:
        await engine.dispose()
        postgres._engine = None


@pytest.mark.asyncio
async def test_create_all_gives_up_after_retries(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    postgres._engine = engine

    calls = {"n": 0}

    from shared_data_api.db.models import Base

    def always_fails(bind, *args, **kwargs):
        calls["n"] += 1
        raise OSError("persistent failure")

    monkeypatch.setattr(Base.metadata, "create_all", always_fails)
    try:
        with pytest.raises(OSError, match="persistent failure"):
            await postgres.create_all(retries=3, backoff_seconds=0.0)
        assert calls["n"] == 3
    finally:
        await engine.dispose()
        postgres._engine = None


@pytest.mark.asyncio
async def test_create_all_succeeds_first_try_on_healthy_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    postgres._engine = engine
    try:
        await postgres.create_all(retries=2, backoff_seconds=0.0)
    finally:
        await engine.dispose()
        postgres._engine = None
