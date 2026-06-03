import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Test settings — set before any module imports config.
os.environ.setdefault("SHARED_DATA_API_POSTGRES_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SHARED_DATA_API_MONGODB_URI", "mongodb://test/test")
os.environ.setdefault("MONGO_INITDB_DATABASE", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-please-change")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRES_MINUTES", "60")
os.environ.setdefault("SHARED_DATA_API_KEY_FNOL", "test-fnol-key")
os.environ.setdefault("SHARED_DATA_API_KEY_CUSTOMER_PORTAL", "test-cp-key")
os.environ.setdefault("SHARED_DATA_API_KEY_AGENT_PORTAL", "test-ap-key")
os.environ.setdefault("DEMO_CUSTOMER_USERNAMES", "alice,bob")
os.environ.setdefault("DEMO_AGENT_USERNAMES", "agent1,agent2")

import structlog  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from shared_data_api.auth.password import hash_password  # noqa: E402
from shared_data_api.config import get_settings  # noqa: E402
from shared_data_api.db import mongo, postgres  # noqa: E402
from shared_data_api.db.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Restore structlog defaults before each test so capture_logs() works.

    The lifespan integration test calls configure_logging() which switches
    structlog into stdlib-bridge mode (ProcessorFormatter). That mode bypasses
    structlog's native processor chain, so structlog.testing.capture_logs()
    cannot intercept events emitted afterward.
    """
    structlog.reset_defaults()
    yield


@pytest_asyncio.fixture
async def settings():
    return get_settings()


@pytest_asyncio.fixture
async def mongo_db():
    client = AsyncMongoMockClient()
    db = client["test"]
    mongo.set_db(db)
    yield db
    mongo.close()


@pytest_asyncio.fixture
async def pg_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    postgres._engine = engine
    postgres._session_factory = factory
    yield factory
    await engine.dispose()
    postgres._engine = None
    postgres._session_factory = None


@pytest_asyncio.fixture
async def seeded_users(mongo_db):
    customer = {
        "username": "alice",
        "password_hash": hash_password("customer"),
        "role": "customer",
        "display_name": "Alice",
    }
    agent = {
        "username": "agent1",
        "password_hash": hash_password("agent"),
        "role": "agent",
        "display_name": "Agent1",
    }
    res_c = await mongo_db.users.insert_one(customer)
    res_a = await mongo_db.users.insert_one(agent)
    return {
        "customer_id": str(res_c.inserted_id),
        "agent_id": str(res_a.inserted_id),
    }


@pytest_asyncio.fixture
async def seeded_policy(mongo_db, seeded_users):
    # Real datetimes (not ISO strings) to match the production seed shape, and a
    # wide effective window so "now" is always inside it.
    from datetime import datetime

    policy = {
        "policy_number": "POL-9001",
        "customer_id": seeded_users["customer_id"],
        "effective_date": datetime(2020, 1, 1),
        "expiration_date": datetime(2030, 1, 1),
        "coverage_type": "auto-comprehensive",
        "premium_cents": 120_000,
        "vehicles": [{"vin": "VIN12345678901234", "make": "Honda", "model": "Civic", "year": 2022}],
    }
    await mongo_db.policies.insert_one(policy)
    return policy


@pytest_asyncio.fixture
async def app_instance(mongo_db, pg_session_factory):
    from shared_data_api.main import create_app

    return create_app()


@pytest_asyncio.fixture
async def client(app_instance):
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def fnol_key():
    return os.environ["SHARED_DATA_API_KEY_FNOL"]


@pytest.fixture
def customer_portal_key():
    return os.environ["SHARED_DATA_API_KEY_CUSTOMER_PORTAL"]


@pytest.fixture
def agent_portal_key():
    return os.environ["SHARED_DATA_API_KEY_AGENT_PORTAL"]
