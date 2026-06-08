"""Tests for the vectorstore factory + degraded-mode detection."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

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


def test_is_embeddings_disabled_returns_false_on_200() -> None:
    """A reachable Ollama that returns 200 to `/api/tags` is healthy."""
    settings = _settings(ollama_base_url="http://ollama-stub:11434")

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=False)
    fake_client.get = MagicMock(return_value=fake_resp)

    with patch("log_dashboard.ingest.vectorstore.httpx.Client", return_value=fake_client):
        assert is_embeddings_disabled(settings) is False


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


def test_strip_url_userinfo_preserves_ipv6_brackets() -> None:
    """IPv6 hosts use bracket syntax (`[::1]`). The redactor must
    preserve the brackets — without them, the URL becomes malformed
    and the probe would fail to parse on retry."""
    assert _strip_url_userinfo("http://user:pass@[::1]:11434") == "http://[::1]:11434"
    # No-userinfo case — brackets still pass through unchanged.
    assert _strip_url_userinfo("http://[::1]:11434") == "http://[::1]:11434"


def test_strip_url_userinfo_leaves_query_string_unchanged() -> None:
    """Only userinfo (`user:pass@`) is stripped — a `?password=secret`
    in the query string is a different shape and must NOT be touched.
    The function's contract is URL-userinfo redaction, not blanket
    secret scrubbing."""
    out = _strip_url_userinfo("http://host:11434/api?password=secret")
    assert out == "http://host:11434/api?password=secret"
    assert "password=secret" in out  # query string survives intact


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
