"""Tests for the vectorstore factory + degraded-mode detection."""

from datetime import UTC, datetime

import pytest

from log_dashboard.config import Settings
from log_dashboard.ingest.vectorstore import (
    _SESSION_SPEND,
    build_vectorstore,
    is_embeddings_disabled,
    metadata_to_log_entry,
    upsert_entries,
)
from log_dashboard.schemas import LogEntry, LogLevel


@pytest.fixture(autouse=True)
def _reset_session_spend():
    """`_SESSION_SPEND` is module-level state; reset around every test so
    one test's spend doesn't leak into the next test's session-total
    assertions."""
    _SESSION_SPEND.tokens = 0
    _SESSION_SPEND.cost_usd = 0.0
    yield
    _SESSION_SPEND.tokens = 0
    _SESSION_SPEND.cost_usd = 0.0


def _settings(**over) -> Settings:
    defaults = dict(
        jwt_secret="test-secret",
        admin_username="admin",
        admin_password="hunter2",
        openai_api_key="sk-test-real-key",
    )
    defaults.update(over)
    return Settings(**defaults)


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


def test_is_embeddings_disabled_flags_empty_and_placeholder_keys() -> None:
    assert is_embeddings_disabled(_settings(openai_api_key="")) is True
    assert is_embeddings_disabled(_settings(openai_api_key="your_openai_api_key_here")) is True
    assert is_embeddings_disabled(_settings(openai_api_key="change_me_to_real_key")) is True
    assert is_embeddings_disabled(_settings(openai_api_key="sk-proj-realxyz")) is False


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
    """The dedup gate is the cost-saver: on a dashboard restart against a
    populated Chroma volume, we MUST NOT pay OpenAI to re-embed the same
    lines. Verified by counting calls on a tracking embedder.
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
    """Any time OpenAI is invoked to embed log lines, the operator gets a
    level-count summary table on stdout AND a structured `embedding_complete`
    log event. Mirrors the user request — visibility into what was paid for.
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
    # Spend rows: 4 entries → some tokens > 0, some USD > 0.
    assert "Tokens" in captured.out
    assert "Cost" in captured.out
    assert "$" in captured.out  # USD prefix on the cost row
    # Session-spend footer.
    assert "Session total (since startup)" in captured.out


def test_upsert_entries_accumulates_session_spend_across_calls(fake_vectorstore, capfd) -> None:
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
                # Format: " Session total (since startup): N,NNN tokens · $0.xxxxxx"
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
    is no OpenAI call to summarise."""
    entries = [_entry(0), _entry(1)]
    upsert_entries(fake_vectorstore, entries)  # first run prints
    capfd.readouterr()  # drain
    second = upsert_entries(fake_vectorstore, entries)
    captured = capfd.readouterr()
    assert second == 0
    assert "Chroma embedding complete" not in captured.out


def test_upsert_entries_no_table_on_dry_run(fake_vectorstore, capfd) -> None:
    """Dry-run short-circuits before any OpenAI call — no table either."""
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
