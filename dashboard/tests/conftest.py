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
# Phase 8 / ADR-017 — point the Ollama probe at an unused localhost port so
# `is_embeddings_disabled` returns True immediately (connection refused, no
# DNS lookup, no 2s timeout per test). Tests that need to exercise the
# probe construct Settings directly with a different URL.
os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:1")
# Phase 8 / ADR-017 — runtime default flipped to False (real Ollama). The
# autouse test default stays True so unit tests don't pay 5-30s of local
# LLM latency per call. The graph still runs end-to-end via the
# `_DryRunChatModel` scripted fake (provider-agnostic).
os.environ.setdefault("DASHBOARD_LLM_DRY_RUN", "true")

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


class FakeEmbeddings:
    """Deterministic stand-in for OllamaEmbeddings — no network, no latency.

    Maps each text to a tiny float vector derived from a SHA-256 hash so
    identical text → identical vector (preserves Chroma's add-with-id
    idempotency). The 8-dim shape is enough for similarity ordering tests
    (real nomic-embed-text returns 768-dim; tests don't need the full dim).
    """

    def __init__(self, dim: int = 8) -> None:
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)

    def _vec(self, text: str) -> list[float]:
        import hashlib

        h = hashlib.sha256(text.encode("utf-8")).digest()
        # Take `dim` bytes and normalize to [0, 1).
        return [b / 255.0 for b in h[: self.dim]]


@pytest.fixture
def fake_embeddings():
    return FakeEmbeddings()


@pytest.fixture
def fake_vectorstore(fake_embeddings):
    """In-memory Chroma backed by chromadb.Client() + FakeEmbeddings.

    Each test gets a fresh ephemeral chromadb client (no persistence between
    tests) and a unique collection name to keep state isolated.
    """
    import uuid

    import chromadb
    from langchain_chroma import Chroma

    client = chromadb.Client()
    return Chroma(
        client=client,
        collection_name=f"test-{uuid.uuid4().hex[:8]}",
        embedding_function=fake_embeddings,
    )


@pytest.fixture
def agent_graph(fake_vectorstore):
    """Compile a fresh LangGraph agent for one test.

    Uses the in-process FakeEmbeddings-backed Chroma so any docs the test
    writes are queryable; uses a fresh `InMemorySaver` so each test owns
    its own thread state.
    """
    from langgraph.checkpoint.memory import InMemorySaver

    from log_dashboard.agent import build_agent_graph
    from log_dashboard.config import get_settings

    return build_agent_graph(get_settings(), fake_vectorstore, InMemorySaver())


@pytest.fixture
def fail_if_real_llm_invoked(monkeypatch):
    """Defence-in-depth: monkeypatch `ChatOllama.__init__` to raise on
    construction. Any test that opts into this fixture asserts that NO real
    LLM call path is touched — the graph must stay on `_DryRunChatModel`.

    Phase 8 / ADR-017 — replaces the Phase 7 `fail_if_openai_invoked`
    fixture. Provider-agnostic in intent; renamed so future provider
    swaps don't require renaming the fixture again.
    """
    from langchain_ollama import ChatOllama

    def _boom(self, *args, **kwargs):
        raise RuntimeError("test attempted to construct ChatOllama")

    monkeypatch.setattr(ChatOllama, "__init__", _boom)
    yield


@pytest.fixture
def log_volume(tmp_path_factory, monkeypatch):
    """Provide a writable log-volume root with the 4 expected file paths.

    Tests write fixture log lines into these files; the dashboard reads them
    via the patched `DASHBOARD_LOG_VOLUME_ROOT` env var. Returns a dict of
    `{app_name: Path}` so tests can append entries directly.
    """
    root = tmp_path_factory.mktemp("logs")
    paths = {
        "shared-data-api": root / "shared-data-api" / "shared-data-api.log",
        "fnol": root / "fnol" / "fnol-app.log",
        "customer-portal": root / "customer-portal" / "customer-portal.log",
        "agent-portal": root / "agent-portal" / "agent-portal.log",
    }
    for p in paths.values():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    monkeypatch.setenv("DASHBOARD_LOG_VOLUME_ROOT", str(root))
    get_settings.cache_clear()
    yield paths
    get_settings.cache_clear()
