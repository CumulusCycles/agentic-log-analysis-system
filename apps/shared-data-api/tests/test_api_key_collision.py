import pytest
import structlog
from fastapi import FastAPI

from shared_data_api.config import get_settings
from shared_data_api.middleware.api_key import APIKeyMiddleware


@pytest.fixture
def colliding_settings(monkeypatch):
    monkeypatch.setenv("SHARED_DATA_API_KEY_FNOL", "shared-secret")
    monkeypatch.setenv("SHARED_DATA_API_KEY_CUSTOMER_PORTAL", "shared-secret")
    monkeypatch.setenv("SHARED_DATA_API_KEY_AGENT_PORTAL", "unique-ap-secret")
    # Defensive: get_settings() is @lru_cache'd; clear so the monkeypatched
    # env vars are read fresh regardless of autouse-fixture ordering.
    get_settings.cache_clear()
    return get_settings()


def test_duplicate_api_keys_emit_warning(colliding_settings):
    app = FastAPI()
    with structlog.testing.capture_logs() as captured:
        APIKeyMiddleware(app, settings=colliding_settings)
    collisions = [e for e in captured if e.get("event") == "api_key_collision"]
    assert len(collisions) == 1
    assert set(collisions[0]["apps"]) == {"fnol", "customer-portal"}
    assert collisions[0]["log_level"] == "warning"


def test_unique_api_keys_emit_no_warning():
    settings = get_settings()
    app = FastAPI()
    with structlog.testing.capture_logs() as captured:
        APIKeyMiddleware(app, settings=settings)
    collisions = [e for e in captured if e.get("event") == "api_key_collision"]
    assert collisions == []
