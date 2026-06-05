"""Unit tests for `query_logs` and `get_app_status` tools.

Drives the tools directly (no graph) and asserts:
- Happy paths return well-shaped results
- Bad inputs surface `tool_error` instead of crashing the graph
- Chroma exceptions degrade to `tool_error: chroma_unreachable`
- `query_logs` honours the `top_k` cap and sanitises `raw` before returning
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

from log_dashboard.agent.tools import build_tools
from log_dashboard.config import get_settings


def _query_logs(tools):
    return next(t for t in tools if t.name == "query_logs")


def _get_app_status(tools):
    return next(t for t in tools if t.name == "get_app_status")


def _seed(store, *, app="fnol", level="ERROR", raw="ERROR fnol request_failed", id_="fnol:1"):
    store.add_documents(
        documents=[
            Document(
                page_content=raw,
                metadata={
                    "id": id_,
                    "app": app,
                    "level": level,
                    "event": "request_failed",
                    "timestamp_iso": "2026-06-05T10:00:00+00:00",
                    "raw": raw,
                },
            )
        ],
        ids=[id_],
    )


def test_query_logs_returns_results_from_chroma(fake_vectorstore) -> None:
    _seed(fake_vectorstore, id_="fnol:1")
    _seed(fake_vectorstore, id_="fnol:2", raw="ERROR fnol timeout")
    tools = build_tools(get_settings(), fake_vectorstore)
    out = _query_logs(tools).invoke({"query": "fnol error", "top_k": 5})
    assert "tool_error" not in out
    assert 1 <= len(out["results"]) <= 5
    first = out["results"][0]
    assert first["app"] == "fnol"
    assert first["level"] == "ERROR"
    assert "score" in first


def test_query_logs_caps_top_k_at_20(fake_vectorstore) -> None:
    for i in range(30):
        _seed(fake_vectorstore, id_=f"fnol:{i}", raw=f"ERROR fnol event_{i}")
    tools = build_tools(get_settings(), fake_vectorstore)
    out = _query_logs(tools).invoke({"query": "fnol", "top_k": 999})
    assert len(out["results"]) <= 20


def test_query_logs_unknown_app_returns_tool_error(fake_vectorstore) -> None:
    tools = build_tools(get_settings(), fake_vectorstore)
    out = _query_logs(tools).invoke({"query": "x", "apps": ["unknown-app"]})
    assert out["results"] == []
    assert "unknown_app" in out["tool_error"]


def test_query_logs_no_vectorstore_returns_tool_error() -> None:
    tools = build_tools(get_settings(), None)
    out = _query_logs(tools).invoke({"query": "anything"})
    assert out["results"] == []
    assert out["tool_error"] == "vectorstore_unavailable"


def test_query_logs_chroma_exception_returns_tool_error(monkeypatch, fake_vectorstore) -> None:
    def _boom(*args, **kwargs):
        raise RuntimeError("chroma is on fire")

    monkeypatch.setattr(fake_vectorstore, "similarity_search_with_score", _boom)
    tools = build_tools(get_settings(), fake_vectorstore)
    out = _query_logs(tools).invoke({"query": "x"})
    assert out["results"] == []
    assert out["tool_error"] == "chroma_unreachable"


def test_query_logs_sanitises_raw_before_returning(fake_vectorstore) -> None:
    """A log line with a JWT-shaped token never reaches the LLM verbatim."""
    secret_raw = (
        "ERROR auth got token "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.abcdefghijklmnopqrstuvwxyz"
    )
    _seed(fake_vectorstore, id_="auth:secret", raw=secret_raw)
    tools = build_tools(get_settings(), fake_vectorstore)
    out = _query_logs(tools).invoke({"query": "auth error"})
    assert out["results"]
    cited_raw = out["results"][0]["raw"]
    assert "[REDACTED]" in cited_raw
    assert "abcdefghijklmnopqrstuvwxyz" not in cited_raw


def test_get_app_status_returns_all_apps_when_no_filter(log_volume) -> None:
    tools = build_tools(get_settings(), None)
    out = _get_app_status(tools).invoke({})
    assert "tool_error" not in out
    names = {a["name"] for a in out["apps"]}
    assert names == {"shared-data-api", "fnol", "customer-portal", "agent-portal"}


def test_get_app_status_unknown_app_returns_tool_error() -> None:
    tools = build_tools(get_settings(), None)
    out = _get_app_status(tools).invoke({"app": "no-such-app"})
    assert out["apps"] == []
    assert "unknown_app" in out["tool_error"]


def test_get_app_status_single_app_filter(log_volume) -> None:
    tools = build_tools(get_settings(), None)
    out = _get_app_status(tools).invoke({"app": "fnol"})
    assert len(out["apps"]) == 1
    assert out["apps"][0]["name"] == "fnol"


@pytest.mark.asyncio
async def test_query_logs_async_wrapper(fake_vectorstore) -> None:
    """The async helper used by tests / future direct callers returns the
    same shape as the synchronous tool path."""
    from log_dashboard.agent.tools import query_logs_async

    _seed(fake_vectorstore, id_="fnol:async")
    out = await query_logs_async(get_settings(), fake_vectorstore, query="anything")
    assert "results" in out
