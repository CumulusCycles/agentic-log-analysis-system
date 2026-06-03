"""Boot the real FastAPI app through its lifespan with stubbed I/O.

The other tests bypass `create_app()` entirely (they set the postgres/mongo
globals directly via fixtures and use ASGITransport without LifespanManager).
This file is the only place that exercises the full startup wiring —
`init_engine` → `create_all` → `init_client` → `ensure_indexes` →
`run_seed_if_empty` → `warn_on_volume_asymmetry` → simulator start — as it
runs in production.
"""

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from shared_data_api.db import mongo


@pytest_asyncio.fixture
async def booted_app(monkeypatch):
    # Replace mongo.init_client with a mongomock-backed equivalent so the
    # lifespan can complete without a real Mongo container.
    async def fake_init_client(uri, database, **kwargs):  # noqa: ARG001
        client = AsyncMongoMockClient()
        mongo._client = client
        mongo._db = client[database]

    monkeypatch.setattr(mongo, "init_client", fake_init_client)

    # SQLite in-memory URL is already set by conftest's env defaults. Postgres
    # init runs unmodified — sqlite+aiosqlite handles the schema fine because
    # models.py uses with_variant for JSONB and BigInteger.
    from shared_data_api.main import create_app

    app = create_app()
    async with LifespanManager(app):
        yield app


@pytest.mark.asyncio
async def test_lifespan_boots_and_health_responds(booted_app):
    transport = ASGITransport(app=booted_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_lifespan_runs_seed(booted_app):
    db = mongo.get_db()
    assert await db.users.count_documents({"role": "customer"}) == 10
    assert await db.users.count_documents({"role": "agent"}) == 5
    assert await db.policies.count_documents({}) == 15


@pytest.mark.asyncio
async def test_lifespan_creates_mongo_indexes(booted_app):
    db = mongo.get_db()
    user_indexes = await db.users.index_information()
    policy_indexes = await db.policies.index_information()
    assert "users_username_unique" in user_indexes
    assert "policies_policy_number_unique" in policy_indexes


@pytest.mark.asyncio
async def test_lifespan_serves_login_end_to_end(booted_app):
    transport = ASGITransport(app=booted_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Default test API key from conftest.
        login = await client.post(
            "/auth/login",
            json={"username": "alice", "password": "customer"},
            headers={"X-API-Key": "test-cp-key"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        me = await client.get(
            "/auth/me",
            headers={"X-API-Key": "test-cp-key", "Authorization": f"Bearer {token}"},
        )
        assert me.status_code == 200
        assert me.json()["username"] == "alice"
