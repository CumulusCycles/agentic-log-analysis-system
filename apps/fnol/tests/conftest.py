import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Test settings — set before any module imports config.
os.environ.setdefault("JWT_SECRET", "test-secret-please-change")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("SHARED_DATA_API_KEY_FNOL", "test-fnol-key")
os.environ.setdefault("SHARED_DATA_API_BASE_URL", "http://shared-data-api-test")

import structlog  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from fnol.auth.jwt import JWT_AUDIENCE, JWT_ISSUER  # noqa: E402
from fnol.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """get_settings() is @lru_cache'd; clear around every test so any
    monkeypatch.setenv done by a fixture or test body reaches Settings()."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Restore structlog defaults before each test so capture_logs() works."""
    structlog.reset_defaults()
    yield


@pytest_asyncio.fixture
async def app_instance():
    from fnol.main import create_app

    return create_app()


@pytest_asyncio.fixture
async def client(app_instance):
    async with LifespanManager(app_instance):
        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def valid_token(settings):
    import time

    import jwt as pyjwt

    now = int(time.time())
    payload = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "user_id": "test-user-id",
        "role": "customer",
        "app": "fnol",
        "iat": now,
        "exp": now + 600,
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
