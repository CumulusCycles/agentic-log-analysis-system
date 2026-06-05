"""End-to-end graph runs against the fake vectorstore + dry-run LLM.

These exercise the full 5-node loop without any network call. They are the
primary regression guard for graph topology and memory persistence.
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage


def _seed_one(store, id_: str = "fnol:int-1"):
    store.add_documents(
        documents=[
            Document(
                page_content="fnol error 500",
                metadata={
                    "id": id_,
                    "app": "fnol",
                    "level": "ERROR",
                    "event": "request_failed",
                    "timestamp_iso": "2026-06-05T10:00:00+00:00",
                    "raw": "ERROR fnol request_failed status=500",
                },
            )
        ],
        ids=[id_],
    )


@pytest.mark.asyncio
async def test_graph_runs_full_loop_against_fake_vectorstore(agent_graph, fake_vectorstore) -> None:
    _seed_one(fake_vectorstore)
    initial = {
        "messages": [HumanMessage(content="why is fnol failing?")],
        "session_id": "sess-1",
        "jwt_sub": "admin",
        "citations": [],
        "dry_run": True,
        "tool_budget_remaining": 4,
        "tool_budget_exhausted": False,
    }
    result = await agent_graph.ainvoke(
        initial, config={"configurable": {"thread_id": "admin:sess-1"}}
    )
    # 4 messages: Human → AI(tool_call) → ToolMessage → AI(final)
    assert len(result["messages"]) == 4
    last = result["messages"][-1]
    assert isinstance(last, AIMessage)
    assert not last.tool_calls
    assert "DRY_RUN" in last.content
    # Citations harvested from the ToolMessage.
    assert len(result["citations"]) >= 1


@pytest.mark.asyncio
async def test_graph_degrades_when_vectorstore_unavailable() -> None:
    """No vectorstore → query_logs returns tool_error, but the graph still
    completes and returns the canned dry-run answer."""
    from langgraph.checkpoint.memory import InMemorySaver

    from log_dashboard.agent import build_agent_graph
    from log_dashboard.config import get_settings

    graph = build_agent_graph(get_settings(), vectorstore=None, checkpointer=InMemorySaver())
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="status?")],
            "session_id": "sess-2",
            "jwt_sub": "admin",
            "citations": [],
            "dry_run": True,
            "tool_budget_remaining": 4,
            "tool_budget_exhausted": False,
        },
        config={"configurable": {"thread_id": "admin:sess-2"}},
    )
    assert isinstance(result["messages"][-1], AIMessage)
    assert "DRY_RUN" in result["messages"][-1].content
    assert result["citations"] == []


@pytest.mark.asyncio
async def test_graph_memory_persists_across_invocations(agent_graph, fake_vectorstore) -> None:
    """Two invocations sharing the same thread_id see each other's messages.

    Proves the InMemorySaver checkpointer is wired correctly — the second
    call's `state["messages"]` includes the first call's user and AI messages.
    """
    _seed_one(fake_vectorstore)
    config = {"configurable": {"thread_id": "admin:shared-sess"}}
    await agent_graph.ainvoke(
        {
            "messages": [HumanMessage(content="first question")],
            "session_id": "shared-sess",
            "jwt_sub": "admin",
            "citations": [],
            "dry_run": True,
            "tool_budget_remaining": 4,
            "tool_budget_exhausted": False,
        },
        config=config,
    )
    result = await agent_graph.ainvoke(
        {
            "messages": [HumanMessage(content="second question")],
            "session_id": "shared-sess",
            "jwt_sub": "admin",
            "citations": [],
            "dry_run": True,
            "tool_budget_remaining": 4,
            "tool_budget_exhausted": False,
        },
        config=config,
    )
    # First call produced 4 messages; second appends 4 more (Human, AI tool, ToolMessage, final AI).
    human_count = sum(1 for m in result["messages"] if isinstance(m, HumanMessage))
    assert human_count >= 2


@pytest.mark.asyncio
async def test_graph_does_not_loop_indefinitely(agent_graph, fake_vectorstore) -> None:
    """The dry-run model terminates after one tool round (the model returns
    the canned final on the 2nd call). Confirms `ingest_node` resets the
    per-request budget to `settings.llm_max_tool_calls_per_request` even
    when the caller passed a higher value."""
    from log_dashboard.config import get_settings

    settings = get_settings()
    _seed_one(fake_vectorstore)
    result = await agent_graph.ainvoke(
        {
            "messages": [HumanMessage(content="hi")],
            "session_id": "sess-budget",
            "jwt_sub": "admin",
            "citations": [],
            "dry_run": True,
            # Pass 10 to confirm ingest's per-request reset overrides it.
            "tool_budget_remaining": 10,
            "tool_budget_exhausted": False,
        },
        config={"configurable": {"thread_id": "admin:sess-budget"}},
    )
    # ingest reset budget to settings.max=4; one correlate pass decremented to 3.
    assert result["tool_budget_remaining"] == settings.llm_max_tool_calls_per_request - 1
    assert result["tool_budget_exhausted"] is False
    # And the loop ran exactly once: 4 messages total.
    assert len(result["messages"]) == 4
