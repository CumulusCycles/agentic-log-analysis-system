"""Tests for GET /api/errors/{entry_id} (Phase 7e PR 4b).

Coverage:
- Auth gate (401 / 401-bad / 200 happy)
- ID-shape validation (400)
- No-vectorstore degraded path (503)
- Entry not in Chroma (404)
- INFO-level entry rejected (404 — defence-in-depth)
- Happy path: dry-run answer + reconstructed entry
- Credential in synthesised raw is redacted in the analysis output
- Token-cap rejection (413) on absurdly long raw lines
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from langchain_core.documents import Document

from log_dashboard.auth.jwt import encode_token
from log_dashboard.config import get_settings
from log_dashboard.ingest.embeddings import make_doc_id


def _seed_chroma_entry(
    store,
    *,
    app: str = "fnol",
    level: str = "ERROR",
    event: str = "request_failed",
    raw: str = "ERROR fnol request_failed status=500",
    timestamp_iso: str = "2026-06-05T10:00:00+00:00",
) -> str:
    """Insert a single document so the route can look it up. Returns the
    content-hash ID under which it was stored, matching what the parser
    would produce for the same `raw`."""
    doc_id = make_doc_id(app, raw)
    store.add_documents(
        documents=[
            Document(
                page_content=raw,
                metadata={
                    "id": doc_id,
                    "app": app,
                    "level": level,
                    "event": event,
                    "source": "prod",
                    "timestamp_iso": timestamp_iso,
                    "raw": raw,
                },
            )
        ],
        ids=[doc_id],
    )
    return doc_id


@pytest_asyncio.fixture
async def client_with_chroma(monkeypatch, fake_vectorstore):
    """AsyncClient where the agent graph + lookup share a fake vectorstore.

    Default lifespan disables embeddings (Ollama unreachable in the test
    env), which leaves `app.state.vectorstore = None` and the agent's
    `query_logs` tool in degraded mode. The Error Detail route needs a live
    vectorstore both for the entry lookup and for the agent's tool path, so
    we patch the two seams the lifespan reads from.
    """
    from log_dashboard import main as main_module

    # v1.1.2 Option A — lifespan now calls `embeddings_state` (three-valued)
    # instead of `is_embeddings_disabled` (binary). Patch the new function
    # to report "ready" so the lifespan wires up the vectorstore + agent.
    monkeypatch.setattr(main_module, "embeddings_state", lambda _settings: "ready")
    monkeypatch.setattr(main_module, "build_vectorstore", lambda _settings, **_kw: fake_vectorstore)
    # Don't spawn the real backfill thread; the fake store is already seeded
    # by individual tests via `_seed_chroma_entry`.
    monkeypatch.setattr(main_module, "run_initial_backfill", lambda *_args, **_kw: [])

    from log_dashboard.main import create_app

    app = create_app()
    async with LifespanManager(app):
        # Verify the override took — guards against the lifespan changing
        # under us in a future PR and silently masking these tests.
        assert app.state.vectorstore is fake_vectorstore
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac, fake_vectorstore


@pytest.mark.asyncio
async def test_errors_no_bearer_returns_401(client) -> None:
    response = await client.get("/api/errors/fnol:abcdef0123456789")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_errors_bad_bearer_returns_401(client) -> None:
    response = await client.get(
        "/api/errors/fnol:abcdef0123456789",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_errors_malformed_id_returns_400(client, valid_token) -> None:
    """A request with a non-content-hash ID is rejected before any Chroma I/O.

    Covers the case where a stale frontend (or a curl typo) passes a
    pre-PR-4b seq-based ID like `fnol:7` or any other shape.
    """
    for bad_id in ("fnol:7", "FNOL:abcdef0123456789", "fnol:nothex", "noprefix", ":missing"):
        response = await client.get(
            f"/api/errors/{bad_id}",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        assert response.status_code == 400, f"expected 400 for {bad_id!r}"
        assert "malformed entry id" in response.json()["detail"]


@pytest.mark.asyncio
async def test_errors_no_vectorstore_returns_503(client, valid_token) -> None:
    """Default lifespan leaves `vectorstore=None` (Ollama unreachable).

    The route surfaces 503 with a message that names the unreachable URL,
    so the operator knows to check OLLAMA_BASE_URL rather than chasing a 404.
    """
    response = await client.get(
        "/api/errors/fnol:abcdef0123456789",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 503
    assert "OLLAMA_BASE_URL" in response.json()["detail"]


@pytest.mark.asyncio
async def test_errors_unknown_id_returns_404(client_with_chroma, valid_token) -> None:
    ac, _store = client_with_chroma
    response = await ac.get(
        "/api/errors/fnol:0000000000000000",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_errors_info_level_entry_is_rejected(client_with_chroma, valid_token) -> None:
    """INFO entries shouldn't enter Chroma via the default ingest gate, but
    we defence-in-depth this in the route — a future config widening must not
    silently widen the Error Detail surface too."""
    ac, store = client_with_chroma
    doc_id = _seed_chroma_entry(store, level="INFO", event="login_success")
    response = await ac.get(
        f"/api/errors/{doc_id}",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 404
    assert "WARN or ERROR" in response.json()["detail"]


@pytest.mark.asyncio
async def test_errors_happy_path_returns_entry_and_analysis(
    client_with_chroma, valid_token, fail_if_real_llm_invoked
) -> None:
    ac, store = client_with_chroma
    doc_id = _seed_chroma_entry(store)

    response = await ac.get(
        f"/api/errors/{doc_id}",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # Entry shape
    entry = body["entry"]
    assert entry["id"] == doc_id
    assert entry["app"] == "fnol"
    assert entry["level"] == "ERROR"
    assert entry["event"] == "request_failed"
    assert "request_failed" in entry["raw"]

    # Analysis shape — dry-run defaults from Settings
    analysis = body["analysis"]
    assert analysis["dry_run"] is True
    assert "DRY_RUN" in analysis["answer"]
    assert isinstance(analysis["citations"], list)
    # No `session_id` on AgentAnalysis — Error Detail flow doesn't expose one
    assert "session_id" not in analysis


@pytest.mark.asyncio
async def test_errors_redacts_credentials_from_analysis_output(
    client_with_chroma, valid_token, fail_if_real_llm_invoked
) -> None:
    """A credential stored in `raw` (e.g. via an upstream-app bug) must not
    survive into the response body. PR 4a's `sanitize_log_raw` is the gate;
    this test asserts the route runs it end-to-end."""
    ac, store = client_with_chroma
    raw_with_secret = (
        "ERROR fnol request_failed authorization=Bearer "
        "sk-veryRealLookingTokenABCDEFGHIJKLMNOP12345"
    )
    doc_id = _seed_chroma_entry(store, raw=raw_with_secret)

    response = await ac.get(
        f"/api/errors/{doc_id}",
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert response.status_code == 200, response.text
    body_text = response.text
    assert "sk-veryRealLookingToken" not in body_text
    assert "ABCDEFGHIJKLMNOP12345" not in body_text


@pytest.mark.asyncio
async def test_errors_token_cap_rejects_huge_raw(
    monkeypatch: pytest.MonkeyPatch, fake_vectorstore, fail_if_real_llm_invoked
) -> None:
    """A massive raw line (large stack trace) blows the input token cap.

    Surfaced as 413 rather than silently truncated. Uses the same builder
    pattern as the chat-cost-caps test — Settings monkeypatch must happen
    before lifespan startup.
    """
    from log_dashboard import main as main_module

    monkeypatch.setenv("DASHBOARD_LLM_MAX_INPUT_TOKENS_PER_REQUEST", "512")
    monkeypatch.setattr(main_module, "embeddings_state", lambda _settings: "ready")
    monkeypatch.setattr(main_module, "build_vectorstore", lambda _settings, **_kw: fake_vectorstore)
    monkeypatch.setattr(main_module, "run_initial_backfill", lambda *_args, **_kw: [])
    get_settings.cache_clear()

    huge_raw = "ERROR fnol stack_trace=" + ("the quick brown fox " * 200)
    doc_id = _seed_chroma_entry(fake_vectorstore, raw=huge_raw)

    settings = get_settings()
    token = encode_token(username="admin", role="admin", settings=settings)

    from log_dashboard.main import create_app

    app = create_app()
    async with LifespanManager(app):
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                f"/api/errors/{doc_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
    assert response.status_code == 413
    assert "token cap" in response.json()["detail"]
