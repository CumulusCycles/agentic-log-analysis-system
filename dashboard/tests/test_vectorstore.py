"""Tests for the vectorstore factory + degraded-mode detection."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from log_dashboard.config import Settings
from log_dashboard.ingest.vectorstore import (
    _SESSION_TOTALS,
    _strip_url_userinfo,
    build_vectorstore,
    is_embeddings_disabled,
    metadata_to_log_entry,
    upsert_entries,
)
from log_dashboard.schemas import LogEntry, LogLevel
from tests._test_helpers import to_alias_kwargs


@pytest.fixture(autouse=True)
def _reset_session_totals():
    """`_SESSION_TOTALS` is module-level state; reset around every test so
    one test's totals don't leak into the next test's session-total
    assertions."""
    _SESSION_TOTALS.tokens = 0
    _SESSION_TOTALS.wall_ms = 0
    yield
    _SESSION_TOTALS.tokens = 0
    _SESSION_TOTALS.wall_ms = 0


def _settings(**over) -> Settings:
    defaults = dict(
        jwt_secret="test-secret",
        admin_username="admin",
        admin_password="hunter2",
    )
    defaults.update(over)
    return Settings(**to_alias_kwargs(defaults))


def _entry(seq: int) -> LogEntry:
    return LogEntry(
        id=f"fnol:{seq}",
        timestamp=datetime(2026, 6, 4, 12, 0, seq, tzinfo=UTC),
        level=LogLevel.INFO,
        app="fnol",
        event="claim_submitted",
        fields={"claim_id": f"C-{seq}"},
        raw=f'{{"event":"claim_submitted","claim_id":"C-{seq}"}}',
    )


def test_is_embeddings_disabled_returns_true_when_ollama_unreachable() -> None:
    """The test conftest defaults `OLLAMA_BASE_URL` to a closed port, so
    `is_embeddings_disabled` should refuse the connection and return True
    immediately."""
    settings = _settings()
    assert is_embeddings_disabled(settings) is True


def test_is_embeddings_disabled_returns_true_on_non_200() -> None:
    """A reachable URL that returns a non-200 status counts as disabled.

    Belt-and-braces for the case where some other service answers on the
    Ollama port but isn't actually Ollama — the dashboard still degrades
    cleanly rather than crashing in the embedder.
    """
    settings = _settings(ollama_base_url="http://example.invalid:11434")

    fake_resp = MagicMock()
    fake_resp.status_code = 502
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.get = MagicMock(return_value=fake_resp)

    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=fake_client):
        assert is_embeddings_disabled(settings) is True


def test_is_embeddings_disabled_returns_false_on_200_with_models_loaded() -> None:
    """A reachable Ollama that returns 200 to `/api/tags` AND lists both
    required models is healthy.

    v1.1.2 Option A — the predicate widened from "daemon reachable" to
    "daemon reachable AND required models in /api/tags". The 200-with-no-
    models case now reports `loading` (covered by the new test below);
    the daemon-only case is no longer "ready".
    """
    settings = _settings(ollama_base_url="http://ollama-stub:11434")

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json = MagicMock(
        return_value={
            "models": [
                {"name": "llama3.1:8b", "model": "llama3.1:8b"},
                {"name": "nomic-embed-text", "model": "nomic-embed-text"},
            ]
        }
    )
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.get = MagicMock(return_value=fake_resp)

    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=fake_client):
        assert is_embeddings_disabled(settings) is False


# v1.1.2 Option A — three-valued `embeddings_state` predicate. The
# lifespan branches on these states (ready / loading / unreachable) to
# decide whether to wire up the vectorstore eagerly, start the promotion
# watchdog, or stay disabled.


def _build_fake_tags_client(status_code: int, json_body: dict | None) -> MagicMock:
    fake_resp = MagicMock()
    fake_resp.status_code = status_code
    if json_body is not None:
        fake_resp.json = MagicMock(return_value=json_body)
    else:
        fake_resp.json = MagicMock(side_effect=ValueError("non-json body"))
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.get = MagicMock(return_value=fake_resp)
    return fake_client


def test_embeddings_state_ready_when_both_models_present() -> None:
    """`/api/tags` lists both required models → `"ready"`. This is the
    happy path the lifespan branches into to build the vectorstore + start
    backfill immediately.
    """
    from log_dashboard.ingest.vectorstore import embeddings_state

    settings = _settings(ollama_base_url="http://ollama-stub:11434")
    client = _build_fake_tags_client(
        200,
        {
            "models": [
                {"name": "llama3.1:8b", "model": "llama3.1:8b"},
                {"name": "nomic-embed-text", "model": "nomic-embed-text"},
                {"name": "other-model", "model": "other-model"},
            ]
        },
    )
    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=client):
        assert embeddings_state(settings) == "ready"


def test_embeddings_state_loading_when_models_missing() -> None:
    """`/api/tags` returns 200 but neither required model is loaded → `"loading"`.
    This is the cold-deploy window where ollama-init is still pulling.
    """
    from log_dashboard.ingest.vectorstore import embeddings_state

    settings = _settings(ollama_base_url="http://ollama-stub:11434")
    client = _build_fake_tags_client(200, {"models": []})
    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=client):
        assert embeddings_state(settings) == "loading"


def test_embeddings_state_ready_when_ollama_normalises_to_latest_tag() -> None:
    """Ollama's `/api/tags` reports tagged names — even when the operator
    pulled `nomic-embed-text` without an explicit tag, the response shows
    `nomic-embed-text:latest`. The dashboard config carries the bare name
    `nomic-embed-text` (matching `ollama pull` usage), so the probe MUST
    treat `name` and `name:latest` as the same model. Without this guard
    the watchdog loops indefinitely after a fresh model pull — the bug
    that motivated the v1.1.2 round-4 cold-deploy live-validation fix.
    """
    from log_dashboard.ingest.vectorstore import embeddings_state

    settings = _settings(ollama_base_url="http://ollama-stub:11434")
    # Mirrors the actual /api/tags JSON observed on a fresh ollama-init pull.
    client = _build_fake_tags_client(
        200,
        {
            "models": [
                {"name": "llama3.1:8b", "model": "llama3.1:8b"},
                {"name": "nomic-embed-text:latest", "model": "nomic-embed-text:latest"},
            ]
        },
    )
    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=client):
        assert embeddings_state(settings) == "ready"


def test_embeddings_state_ready_when_explicit_latest_tag_in_settings() -> None:
    """Inverse of the previous test — operator pulled `nomic-embed-text:latest`
    explicitly AND configured it with the tag. Must also report ready.
    """
    from log_dashboard.ingest.vectorstore import embeddings_state

    settings = _settings(
        ollama_base_url="http://ollama-stub:11434",
        dashboard_embed_model="nomic-embed-text:latest",
    )
    client = _build_fake_tags_client(
        200,
        {
            "models": [
                {"name": "llama3.1:8b", "model": "llama3.1:8b"},
                {"name": "nomic-embed-text:latest", "model": "nomic-embed-text:latest"},
            ]
        },
    )
    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=client):
        assert embeddings_state(settings) == "ready"


def test_embeddings_state_does_not_match_arbitrary_tag_substitution() -> None:
    """The `:latest` normalisation is intentionally narrow — `llama3.1:8b`
    (an EXPLICIT tag) must NOT silently match `llama3.1:latest` if that's
    what's loaded. Pin this so a future "be lenient" refactor doesn't
    mistakenly accept a wrong-version model.
    """
    from log_dashboard.ingest.vectorstore import embeddings_state

    settings = _settings(ollama_base_url="http://ollama-stub:11434")
    client = _build_fake_tags_client(
        200,
        {
            "models": [
                {"name": "llama3.1:latest", "model": "llama3.1:latest"},
                {"name": "nomic-embed-text:latest", "model": "nomic-embed-text:latest"},
            ]
        },
    )
    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=client):
        # `llama3.1:8b` is missing (only `llama3.1:latest` is loaded).
        assert embeddings_state(settings) == "loading"


def test_embeddings_state_loading_when_only_llm_present() -> None:
    """Partial-pull edge case — LLM is in but embed model isn't.
    Still `"loading"` (need BOTH).
    """
    from log_dashboard.ingest.vectorstore import embeddings_state

    settings = _settings(ollama_base_url="http://ollama-stub:11434")
    client = _build_fake_tags_client(
        200, {"models": [{"name": "llama3.1:8b", "model": "llama3.1:8b"}]}
    )
    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=client):
        assert embeddings_state(settings) == "loading"


def test_embeddings_state_unreachable_on_connection_error() -> None:
    """Daemon unreachable (connection refused / DNS / timeout) → `"unreachable"`.
    The lifespan does NOT start the promotion watchdog for this state — a
    bad URL won't fix itself.
    """
    from log_dashboard.ingest.vectorstore import embeddings_state

    settings = _settings(ollama_base_url="http://127.0.0.1:1")
    # The conftest already points OLLAMA_BASE_URL at a closed port, but
    # we patch httpx.Client explicitly here so the test is self-contained.
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.get = MagicMock(side_effect=httpx.ConnectError("refused"))
    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=fake_client):
        assert embeddings_state(settings) == "unreachable"


def test_embeddings_state_unreachable_on_non_200() -> None:
    """Any non-200 from `/api/tags` (auth required, etc.) → `"unreachable"`."""
    from log_dashboard.ingest.vectorstore import embeddings_state

    settings = _settings(ollama_base_url="http://ollama-stub:11434")
    client = _build_fake_tags_client(403, None)
    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=client):
        assert embeddings_state(settings) == "unreachable"


def test_embeddings_state_unreachable_on_unparseable_body() -> None:
    """200 with non-JSON body → `"unreachable"` (treats as broken probe)."""
    from log_dashboard.ingest.vectorstore import embeddings_state

    settings = _settings(ollama_base_url="http://ollama-stub:11434")
    client = _build_fake_tags_client(200, None)
    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=client):
        assert embeddings_state(settings) == "unreachable"


def test_embeddings_state_loading_respects_custom_model_settings() -> None:
    """The probe reads `dashboard_llm_model` + `dashboard_embed_model` from
    Settings, so a future qwen2.5:14b trial needs the names updated in env,
    not the predicate code. This pins the wiring.
    """
    from log_dashboard.ingest.vectorstore import embeddings_state

    settings = _settings(
        ollama_base_url="http://ollama-stub:11434",
        dashboard_llm_model="qwen2.5:14b",
        dashboard_embed_model="nomic-embed-text",
    )
    # `/api/tags` carries the old llama3.1 but not the qwen — `"loading"`.
    client = _build_fake_tags_client(
        200,
        {
            "models": [
                {"name": "llama3.1:8b", "model": "llama3.1:8b"},
                {"name": "nomic-embed-text", "model": "nomic-embed-text"},
            ]
        },
    )
    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=client):
        assert embeddings_state(settings) == "loading"


def test_build_vectorstore_against_in_memory_client(fake_embeddings) -> None:
    import chromadb
    from langchain_chroma import Chroma

    settings = _settings(chroma_collection="vs-test")
    store = build_vectorstore(
        settings,
        client=chromadb.Client(),
        embedding_function=fake_embeddings,
    )
    assert isinstance(store, Chroma)
    # Round-trip: add one entry, search for it.
    upserted = upsert_entries(store, [_entry(0)])
    assert upserted == 1
    hits = store.similarity_search("claim", k=5)
    assert len(hits) == 1
    assert hits[0].metadata["app"] == "fnol"


def test_upsert_entries_is_idempotent_by_content_hash_id(fake_vectorstore) -> None:
    entries = [_entry(i) for i in range(3)]
    upsert_entries(fake_vectorstore, entries)
    upsert_entries(fake_vectorstore, entries)  # same content → same IDs
    upsert_entries(fake_vectorstore, entries)
    # Chroma collection should hold exactly 3 docs despite three upsert passes.
    coll = fake_vectorstore._collection  # langchain-chroma exposes the chromadb Collection
    assert coll.count() == 3


def test_upsert_entries_skips_already_indexed_to_avoid_re_embedding() -> None:
    """The dedup gate avoids redundant embedding work: on a dashboard
    restart against a populated Chroma volume, we MUST NOT re-embed the
    same lines. Phase 7 framed this as a cost saver against OpenAI; Phase
    8 / ADR-017 makes it a performance saver against Ollama latency.
    Verified by counting calls on a tracking embedder.
    """
    import uuid

    import chromadb
    from langchain_chroma import Chroma

    class CountingEmbeddings:
        def __init__(self) -> None:
            self.embed_documents_calls = 0
            self.embed_query_calls = 0

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            self.embed_documents_calls += 1
            return [[float(i)] for i, _ in enumerate(texts)]

        def embed_query(self, text: str) -> list[float]:
            self.embed_query_calls += 1
            return [0.0]

    embedder = CountingEmbeddings()
    store = Chroma(
        client=chromadb.Client(),
        collection_name=f"dedup-{uuid.uuid4().hex[:8]}",
        embedding_function=embedder,
    )
    entries = [_entry(i) for i in range(5)]

    first_embedded = upsert_entries(store, entries)
    assert first_embedded == 5
    assert embedder.embed_documents_calls == 1  # one batch

    # Restart simulation: same content, already in Chroma. embed_documents
    # must NOT be called again — that's the whole point.
    second_embedded = upsert_entries(store, entries)
    assert second_embedded == 0
    assert embedder.embed_documents_calls == 1  # unchanged

    # Mixed batch: 3 already-present + 2 new — embed only the 2 new.
    extra = [_entry(i) for i in range(5, 7)]
    third_embedded = upsert_entries(store, entries + extra)
    assert third_embedded == 2
    assert embedder.embed_documents_calls == 2  # one more batch fired


def test_upsert_entries_prints_level_count_table_after_embedding(
    fake_vectorstore, capfd, caplog
) -> None:
    """Any time the embedder is invoked, the operator gets a level-count
    summary table on stdout AND a structured `embedding_complete` log
    event. Phase 8 / ADR-017 — table shows wall-time instead of USD cost.
    """
    entries = [
        _entry(0),  # INFO
        LogEntry(
            id="fnol:warn1",
            timestamp=datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC),
            level=LogLevel.WARN,
            app="fnol",
            event="request",
            fields={},
            raw='{"event":"request","level":"warning"}',
        ),
        LogEntry(
            id="fnol:err1",
            timestamp=datetime(2026, 6, 5, 12, 1, 0, tzinfo=UTC),
            level=LogLevel.ERROR,
            app="fnol",
            event="request_failed",
            fields={},
            raw='{"event":"request_failed","level":"error"}',
        ),
        LogEntry(
            id="fnol:err2",
            timestamp=datetime(2026, 6, 5, 12, 2, 0, tzinfo=UTC),
            level=LogLevel.ERROR,
            app="fnol",
            event="request_failed",
            fields={},
            raw='{"event":"request_failed","level":"error","second":true}',
        ),
    ]
    embedded = upsert_entries(fake_vectorstore, entries)
    assert embedded == 4

    # The ASCII table goes to stdout via print().
    captured = capfd.readouterr()
    assert "Chroma embedding complete" in captured.out
    assert "fnol" in captured.out
    # Standard rows present even when count is 0 → consistent shape.
    assert "DEBUG" in captured.out
    assert "INFO" in captured.out
    assert "WARN" in captured.out
    assert "ERROR" in captured.out
    assert "TOTAL" in captured.out
    # Counts: 1 INFO, 1 WARN, 2 ERROR, 0 DEBUG, total 4.
    assert "| INFO    |                1 |" in captured.out
    assert "| WARN    |                1 |" in captured.out
    assert "| ERROR   |                2 |" in captured.out
    assert "| TOTAL   |                4 |" in captured.out
    # Throughput rows: tokens > 0 and wall_ms reported (Phase 8 — no USD).
    assert "Tokens" in captured.out
    assert "Wall" in captured.out
    assert " ms" in captured.out  # wall-time suffix
    assert "$" not in captured.out  # cost columns retired per ADR-017
    # Session-totals footer.
    assert "Session total (since startup)" in captured.out


def test_upsert_entries_batch_wall_ms_is_at_least_one(fake_vectorstore, capfd) -> None:
    """v1.1.2 — fast batches (a single entry on a fake vectorstore can
    complete sub-millisecond on modern hardware) MUST report wall-time
    `>= 1 ms` in the embed-summary table. Without `max(1, round(...))`,
    `int()` floor-truncated sub-ms elapsed time to `0` — confusing
    operators reading the table (`0 ms` reads like "didn't measure").

    Asserts via the stdout print pipeline (matches the existing tests in
    this file). The Wall row format is `| Wall    |             N ms |`
    where N is right-justified in a 13-char column.
    """
    import re

    embedded = upsert_entries(fake_vectorstore, [_entry(0)])
    assert embedded == 1

    out = capfd.readouterr().out

    # Find the Wall row in the table — it always renders as `| Wall    |  <N> ms |`.
    wall_match = re.search(r"\|\s*Wall\s*\|\s*(\d+)\s*ms\s*\|", out)
    assert wall_match is not None, "Wall row missing from embed-summary table"
    batch_wall_ms = int(wall_match.group(1))
    # `max(1, round(...))` guarantees a measured operation always shows
    # at least 1ms; 0 is reserved for "not measured" (which is unreachable
    # here because the embed loop completed).
    assert batch_wall_ms >= 1, f"expected batch_wall_ms >= 1, got {batch_wall_ms}"

    # The session-totals footer also surfaces a wall-time number — same
    # truncation risk if the running total accumulated `0` from a fast
    # first batch. Format: `Session total (since startup): N tokens · N ms`.
    session_match = re.search(r"Session total .*?(\d+)\s+ms", out)
    assert session_match is not None, "session-totals footer missing"
    session_wall_ms = int(session_match.group(1))
    assert session_wall_ms >= 1, f"expected session_wall_ms >= 1, got {session_wall_ms}"


def test_upsert_entries_accumulates_session_totals_across_calls(fake_vectorstore, capfd) -> None:
    """Two successive upserts (different content) drive the running session
    total — the second table's session row should show MORE tokens than
    the first."""
    upsert_entries(fake_vectorstore, [_entry(0)])
    first = capfd.readouterr().out
    upsert_entries(fake_vectorstore, [_entry(1), _entry(2)])
    second = capfd.readouterr().out

    # Both tables include the session footer.
    assert "Session total (since startup)" in first
    assert "Session total (since startup)" in second

    # Extract the session token count from each footer.
    def _session_tokens(text: str) -> int:
        for line in text.splitlines():
            if "Session total" in line:
                # Format: " Session total (since startup): N,NNN tokens · NN ms"
                return int(line.split(":", 1)[1].strip().split()[0].replace(",", ""))
        raise AssertionError("no session footer in output")

    assert _session_tokens(second) > _session_tokens(first)


def test_metadata_to_log_entry_round_trips_source_field(fake_vectorstore) -> None:
    """The `source` field on a parsed entry must survive the Chroma
    metadata write → read round-trip. Pre-PR-4b bug: the reader dropped
    `source`, so the LogEntry.source="prod" default silently overrode
    whatever the parser had tagged (synthetic / health / unknown)."""
    from log_dashboard.ingest.embeddings import make_metadata

    entry = LogEntry(
        id="fnol:test-rt",
        timestamp=datetime(2026, 6, 5, 12, 0, 0, tzinfo=UTC),
        level=LogLevel.WARN,
        app="fnol",
        event="sda_upstream_rejected",
        fields={"target": "/auth/login"},
        raw='{"event":"sda_upstream_rejected","source":"synthetic"}',
        source="synthetic",
    )
    md = make_metadata(entry)
    assert md["source"] == "synthetic"  # written correctly
    recovered = metadata_to_log_entry(md)
    assert recovered is not None
    assert recovered.source == "synthetic"  # read back correctly (PR 4b fix)


def test_upsert_entries_no_table_when_nothing_embedded(fake_vectorstore, capfd) -> None:
    """Re-running an upsert with all-deduped entries skips the table — there
    is no embed call to summarise."""
    entries = [_entry(0), _entry(1)]
    upsert_entries(fake_vectorstore, entries)  # first run prints
    capfd.readouterr()  # drain
    second = upsert_entries(fake_vectorstore, entries)
    captured = capfd.readouterr()
    assert second == 0
    assert "Chroma embedding complete" not in captured.out


def test_upsert_entries_no_table_on_dry_run(fake_vectorstore, capfd) -> None:
    """Dry-run short-circuits before any embed call — no table either."""
    upsert_entries(fake_vectorstore, [_entry(0), _entry(1)], dry_run=True)
    captured = capfd.readouterr()
    assert "Chroma embedding complete" not in captured.out


def test_upsert_entries_handles_empty_list() -> None:
    # No-op guard so the watcher can safely call this with no new lines.
    import chromadb
    from langchain_chroma import Chroma

    store = Chroma(
        client=chromadb.Client(),
        collection_name="vs-empty",
        embedding_function=(
            pytest.importorskip("langchain_core").embeddings.Embeddings
            if False
            else _make_noop_embeddings()
        ),
    )
    assert upsert_entries(store, []) == 0


def _make_noop_embeddings():
    class _Stub:
        def embed_documents(self, texts):
            return [[0.0] for _ in texts]

        def embed_query(self, text):
            return [0.0]

    return _Stub()


# ---------------------------------------------------------------------------
# _strip_url_userinfo — credential-redaction helper for Ollama probe logs
# (defence-in-depth against operator misconfiguring `OLLAMA_BASE_URL`)
# ---------------------------------------------------------------------------


def test_strip_url_userinfo_removes_user_and_password() -> None:
    assert _strip_url_userinfo("http://user:pass@host:11434") == "http://host:11434"


def test_strip_url_userinfo_removes_user_only() -> None:
    """RFC 3986 allows user-only userinfo (no password). Both must be
    stripped from the netloc before logging."""
    assert _strip_url_userinfo("http://user@host:11434") == "http://host:11434"


def test_strip_url_userinfo_removes_percent_encoded_credentials() -> None:
    """Operators can percent-encode `@`, `:`, `/` in credentials. The
    redactor must still recognise the userinfo segment and strip it
    (the password may contain `%40` for `@`, etc.)."""
    out = _strip_url_userinfo("http://user:p%40ssword@host:11434")
    assert out == "http://host:11434"
    assert "p%40" not in out
    assert "password" not in out


def test_strip_url_userinfo_preserves_path_and_scheme() -> None:
    assert _strip_url_userinfo("https://user:pass@host:11434/api/v1") == "https://host:11434/api/v1"


def test_strip_url_userinfo_passthrough_when_no_userinfo() -> None:
    """A clean URL must round-trip unchanged — no spurious netloc
    rewrites that could alter what the operator sees in logs."""
    assert _strip_url_userinfo("http://ollama:11434") == "http://ollama:11434"
    assert _strip_url_userinfo("https://example.com/path") == "https://example.com/path"


def test_strip_url_userinfo_passthrough_for_garbage_input() -> None:
    """Malformed strings (not URLs at all) must pass through without
    crashing. `urlparse` is permissive but we double-defend with a
    try/except in the helper."""
    # urlparse accepts these without raising; we just want no crash.
    assert _strip_url_userinfo("") == ""
    assert _strip_url_userinfo("not-a-url") == "not-a-url"
    assert _strip_url_userinfo("///") == "///"


def test_strip_url_userinfo_redacts_on_urlparse_failure(monkeypatch) -> None:
    """v1.1.2: if `urlparse` itself raises (rare but possible on truly
    malformed input), the function MUST return a constant placeholder
    rather than the original input — otherwise a credentialed URL that
    confuses `urlparse` would silently echo its credentials.

    v1.1.2 round-3 — also asserts the patched `urlparse` actually fires.
    Without the call-count guard, a future refactor that stops calling
    `urlparse` would silently slot the patch in but never trigger it,
    masking the redaction-path test as a no-op.
    """
    import log_dashboard.ingest.vectorstore as vs_mod

    calls: list[str] = []

    def _boom(arg: str):
        calls.append(arg)
        raise ValueError("simulated urlparse failure")

    monkeypatch.setattr(vs_mod, "urlparse", _boom)
    out = _strip_url_userinfo("http://leaky_user:leaky_pass@host:11434")
    assert calls, "urlparse was never called — redaction path not exercised"
    assert out == "<unparseable-url-redacted>"
    assert "leaky_user" not in out
    assert "leaky_pass" not in out


def test_strip_url_userinfo_redacts_on_urlunparse_failure(monkeypatch) -> None:
    """v1.1.2: if `urlunparse` raises during netloc reassembly, the
    function MUST return the constant placeholder rather than the
    original input. Same credential-echo risk as the urlparse path.

    v1.1.2 round-3 — call-count guard mirrors the urlparse-failure test.
    """
    import log_dashboard.ingest.vectorstore as vs_mod

    calls: list[object] = []

    def _boom(arg):
        calls.append(arg)
        raise ValueError("simulated urlunparse failure")

    monkeypatch.setattr(vs_mod, "urlunparse", _boom)
    out = _strip_url_userinfo("http://leaky_user:leaky_pass@host:11434")
    assert calls, "urlunparse was never called — redaction path not exercised"
    assert out == "<unparseable-url-redacted>"
    assert "leaky_user" not in out
    assert "leaky_pass" not in out


def test_strip_url_userinfo_redacts_on_unexpected_exception_type(monkeypatch) -> None:
    """v1.1.2 post-review hardening — the except clause was broadened to
    `except Exception` so future Python versions or unexpected input
    types can't slip past the (ValueError, AttributeError) tuple. This
    test pins a non-tuple exception type (RuntimeError) and verifies the
    redaction still fires.

    v1.1.2 round-3 — call-count guard mirrors the other two parse-failure
    tests.
    """
    import log_dashboard.ingest.vectorstore as vs_mod

    calls: list[str] = []

    def _boom(arg: str):
        calls.append(arg)
        raise RuntimeError("hypothetical future-Python urlparse error")

    monkeypatch.setattr(vs_mod, "urlparse", _boom)
    out = _strip_url_userinfo("http://leaky_user:leaky_pass@host:11434")
    assert calls, "urlparse was never called — redaction path not exercised"
    assert out == "<unparseable-url-redacted>"
    assert "leaky_user" not in out
    assert "leaky_pass" not in out


def test_strip_url_userinfo_preserves_ipv6_brackets() -> None:
    """IPv6 hosts use bracket syntax (`[::1]`). The redactor must
    preserve the brackets — without them, the URL becomes malformed
    and the probe would fail to parse on retry."""
    out_with_userinfo = _strip_url_userinfo("http://user:pass@[::1]:11434")
    assert out_with_userinfo == "http://[::1]:11434"
    assert "[::1]" in out_with_userinfo  # explicit: brackets present in output
    # No-userinfo case — brackets still pass through unchanged.
    out_no_userinfo = _strip_url_userinfo("http://[::1]:11434")
    assert out_no_userinfo == "http://[::1]:11434"
    assert "[::1]" in out_no_userinfo


def test_strip_url_userinfo_leaves_query_string_unchanged() -> None:
    """Only userinfo (`user:pass@`) is stripped — secret-shaped values
    in the query string are a different shape and must NOT be touched.
    The function's contract is URL-userinfo redaction, not blanket
    secret scrubbing. Covers several common parameter names + a
    percent-encoded `@` in the value (which should NOT be confused
    with userinfo)."""
    cases = [
        "http://host:11434/api?password=secret",
        "http://host:11434/api?api_key=xyz&token=abc",
        "http://host:11434/api?user=name%40example.com",  # percent-encoded @
    ]
    for url in cases:
        assert _strip_url_userinfo(url) == url, f"query string altered for {url}"


def test_strip_url_userinfo_does_not_log_credentials_through_probe(monkeypatch, caplog) -> None:
    """End-to-end guarantee: `is_embeddings_disabled` must NOT emit the
    raw userinfo on the structured log line, even when the probe fails
    against a credentialed URL.

    Constructs a Settings object pointing at an unroutable URL with
    credentials, calls the probe, and asserts no part of the credential
    appears in any captured log record's serialised form.
    """
    settings = _settings(ollama_base_url="http://leaky_user:leaky_pass@127.0.0.1:1")

    import logging

    caplog.set_level(logging.INFO)
    assert is_embeddings_disabled(settings) is True

    # Defensive: check the message AND every value in the record dict
    # individually, in case a future structlog formatter wraps a value
    # in an object whose `str()` masks the underlying credential.
    for rec in caplog.records:
        assert "leaky_user" not in rec.getMessage()
        assert "leaky_pass" not in rec.getMessage()
        for val in rec.__dict__.values():
            assert "leaky_user" not in str(val)
            assert "leaky_pass" not in str(val)


def test_build_vectorstore_forwards_timeout_to_ollama_embeddings(monkeypatch) -> None:
    """v1.1.1 symmetry guard: `OllamaEmbeddings` must receive the same
    `client_kwargs={"timeout": N}` plumbing that `ChatOllama` got in v1.1.0.

    Without this, backfill / watcher embedding calls would hang indefinitely
    on the default httpx 5-second read timeout when Ollama stalls, while the
    chat path remains bounded at `llm_timeout_seconds`. Asymmetric blind
    spot. See [[reference_langchain_ollama_timeout_kwarg]] for the
    silent-absorption gotcha — same shape applies to `OllamaEmbeddings`.
    """
    import chromadb

    captured: dict[str, object] = {}

    class _Spy:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def embed_documents(self, texts):  # noqa: ANN001, ANN201 — stub
            return [[0.0] for _ in texts]

        def embed_query(self, text):  # noqa: ANN001, ANN201 — stub
            return [0.0]

    monkeypatch.setattr("log_dashboard.ingest.vectorstore.OllamaEmbeddings", _Spy)

    settings = _settings(llm_timeout_seconds=77, chroma_collection="vs-timeout-test")
    build_vectorstore(settings, client=chromadb.Client())

    assert captured.get("client_kwargs") == {"timeout": 77}
    assert captured.get("base_url") == settings.ollama_base_url
    assert captured.get("model") == settings.dashboard_embed_model


def test_build_vectorstore_forwards_chroma_timeout_to_http_client(
    monkeypatch, fake_embeddings
) -> None:
    """v1.1.2 — `chroma_timeout_seconds` MUST reach the underlying
    `chromadb.HttpClient` via `ChromaClientSettings`. A typo on the
    setting name (e.g., `chroma_query_request_timeoutsec_onds`) would
    silently no-op — `chromadb.config.Settings` accepts arbitrary kwargs
    that don't match a defined field, which would mean the timeout never
    binds to httpx.

    Asserts the spy's captured `settings` arg has BOTH the query and
    sysdb request-timeout fields set to the configured value. Closes the
    integration gap that the bounds test (`test_settings_bounds.py`)
    doesn't cover — that test only pins env→Settings, not Settings→Chroma.
    """
    captured: dict[str, object] = {}

    class _FakeChromaClient:
        """Stand-in for `chromadb.HttpClient` — captures the constructor
        kwargs and exposes the minimum surface `Chroma()` needs to wrap
        it (collection access via `get_or_create_collection`).
        """

        def __init__(self, host=None, port=None, settings=None, **kwargs):  # noqa: ANN001
            captured["host"] = host
            captured["port"] = port
            captured["settings"] = settings
            captured["extra"] = kwargs

        def get_or_create_collection(self, *args, **kwargs):  # noqa: ANN001
            # langchain-chroma calls this during Chroma() init; return a
            # minimal stub that won't crash subsequent .add/.query attempts.
            import chromadb

            real = chromadb.Client()
            return real.get_or_create_collection(*args, **kwargs)

    monkeypatch.setattr("log_dashboard.ingest.vectorstore.chromadb.HttpClient", _FakeChromaClient)

    settings = _settings(
        chroma_timeout_seconds=42,
        chroma_url="http://chroma-test:8000",
        chroma_collection="vs-chroma-timeout-test",
    )
    # No `client=` so the HttpClient construction path runs.
    build_vectorstore(settings, embedding_function=fake_embeddings)

    assert captured.get("host") == "chroma-test"
    assert captured.get("port") == 8000
    chroma_settings = captured.get("settings")
    assert chroma_settings is not None, "ChromaClientSettings must be forwarded to HttpClient"
    assert chroma_settings.chroma_query_request_timeout_seconds == 42
    assert chroma_settings.chroma_sysdb_request_timeout_seconds == 42
