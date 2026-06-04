import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Test settings — set before any module imports config.
os.environ.setdefault("DASHBOARD_JWT_SECRET", "test-dashboard-secret-please-change")
os.environ.setdefault("DASHBOARD_JWT_ALGORITHM", "HS256")
os.environ.setdefault("DASHBOARD_JWT_EXPIRES_MINUTES", "60")
os.environ.setdefault("DASHBOARD_ADMIN_USERNAME", "admin")
os.environ.setdefault("DASHBOARD_ADMIN_PASSWORD", "hunter2")
os.environ.setdefault("DASHBOARD_CHROMA_URL", "http://chroma:8000")

import structlog  # noqa: E402

from log_dashboard.auth.jwt import encode_token  # noqa: E402
from log_dashboard.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """get_settings() is @lru_cache'd; clear it around every test so any
    monkeypatch.setenv done by a fixture or test body reaches Settings()."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Restore structlog defaults before each test so capture_logs() works.

    create_app() calls configure_logging() which switches structlog into
    stdlib-bridge mode (ProcessorFormatter). That mode bypasses structlog's
    native processor chain, so structlog.testing.capture_logs() cannot
    intercept events emitted afterward.
    """
    structlog.reset_defaults()
    yield


@pytest_asyncio.fixture
async def app_instance():
    from log_dashboard.main import create_app

    app = create_app()
    async with LifespanManager(app):
        yield app


@pytest_asyncio.fixture
async def client(app_instance):
    # raise_app_exceptions=False so the Exception catch-all handler returns
    # 500 instead of the exception re-raising into pytest. See
    # `reference_asgi_transport_raise_app_exceptions` memory.
    transport = ASGITransport(app=app_instance, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_token():
    settings = get_settings()
    return encode_token(username="admin", role="admin", settings=settings)
