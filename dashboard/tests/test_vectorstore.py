"""Tests for the vectorstore factory + degraded-mode detection."""

from datetime import UTC, datetime

import pytest

from log_dashboard.config import Settings
from log_dashboard.ingest.vectorstore import (
    build_vectorstore,
    is_embeddings_disabled,
    upsert_entries,
)
from log_dashboard.schemas import LogEntry, LogLevel


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
