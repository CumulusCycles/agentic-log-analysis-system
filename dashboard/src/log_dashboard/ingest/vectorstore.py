"""Chroma + OpenAI embeddings client factory + upsert helper."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from log_dashboard.config import Settings
from log_dashboard.ingest.embeddings import (
    make_doc_id,
    make_metadata,
    make_page_content,
)

if TYPE_CHECKING:
    from log_dashboard.schemas import LogEntry


# Strings we treat as "operator hasn't set this yet" — the same prefixes the
# `.env.example` template uses for placeholder values.
_PLACEHOLDER_PREFIXES = ("your_", "change_me")


def is_embeddings_disabled(settings: Settings) -> bool:
    """True when `OPENAI_API_KEY` is empty or still the .env.example placeholder.

    The dashboard must stay usable for `/api/logs` and `/api/status` even
    without an OpenAI key (ADR-006 spirit). When disabled, the lifespan skips
    backfill + watcher, and `/api/logs/search` returns 503.
    """
    return _looks_like_placeholder(settings.openai_api_key)


def configure_langsmith(settings: Settings) -> None:
    """Programmatically enable LangSmith tracing when the API key looks real.

    LangChain auto-tracing requires BOTH `LANGSMITH_TRACING=true` and
    `LANGSMITH_API_KEY` in the process env. We set TRACING here so operators
    only need to provide the key.
    """
    if _looks_like_placeholder(settings.langsmith_api_key):
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project


def build_vectorstore(
    settings: Settings,
    *,
    client: chromadb.ClientAPI | None = None,
    embedding_function: object | None = None,
) -> Chroma:
    """Construct a langchain-chroma store wrapping the live `chroma` server.

    Tests pass `client=chromadb.Client()` (in-memory) and a stub
    `embedding_function` to avoid network + OpenAI calls. Production calls
    with no kwargs to get the live HttpClient + real OpenAI embeddings.
    """
    if embedding_function is None:
        embedding_function = OpenAIEmbeddings(
            api_key=settings.openai_api_key,
            model=settings.openai_embedding_model,
        )
    if client is None:
        host, port = _parse_chroma_url(settings.chroma_url)
        client = chromadb.HttpClient(host=host, port=port)
    return Chroma(
        client=client,
        collection_name=settings.chroma_collection,
        embedding_function=embedding_function,
    )


def upsert_entries(
    store: Chroma,
    entries: list[LogEntry],
    *,
    batch_size: int = 100,
    dry_run: bool = False,
) -> int:
    """Embed + add entries to the store, batched.

    Before each batch is sent to the embedder, we query Chroma for IDs that
    already exist and skip those — content-stable IDs make this safe and it
    avoids paying OpenAI to re-embed lines we already have. This is the
    difference between a $0.01 restart and a $0 restart.

    When `dry_run=True`, the function short-circuits: no Chroma read, no
    OpenAI call, no upsert. Returns 0 so the caller can log that nothing was
    persisted. Use this from the lifespan when `DASHBOARD_INGEST_DRY_RUN=true`
    to preview ingestion gate behavior without spending any tokens.

    Returns the number of entries actually embedded (excluding dedupes; 0 on
    dry_run).
    """
    if not entries or dry_run:
        return 0
    embedded = 0
    for i in range(0, len(entries), batch_size):
        chunk = entries[i : i + batch_size]
        ids = [make_doc_id(e.app, e.raw) for e in chunk]
        existing = store._collection.get(ids=ids, include=[])
        existing_ids = set(existing.get("ids", []))
        new_pairs = [
            (e, doc_id) for e, doc_id in zip(chunk, ids, strict=False) if doc_id not in existing_ids
        ]
        if not new_pairs:
            continue
        new_entries = [pair[0] for pair in new_pairs]
        new_ids = [pair[1] for pair in new_pairs]
        docs = [
            Document(page_content=make_page_content(e), metadata=make_metadata(e))
            for e in new_entries
        ]
        store.add_documents(documents=docs, ids=new_ids)
        embedded += len(new_entries)
    return embedded


def _parse_chroma_url(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    return parsed.hostname or "chroma", parsed.port or 8000


def _looks_like_placeholder(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    return any(stripped.startswith(p) for p in _PLACEHOLDER_PREFIXES)
