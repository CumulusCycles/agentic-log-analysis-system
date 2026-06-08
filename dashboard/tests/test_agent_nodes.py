"""Unit tests for the agent graph's nodes — exercised directly, no graph.

Each node is a `(state) -> dict[str, Any]` async function. We drive each with
a synthetic `AgentState` and assert the state mutation; no LLM network call,
no Chroma. Dry-run is the default test-scope posture (autouse env in
`conftest.py`) so `_DryRunChatModel` takes over from `ChatOllama`
automatically.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from log_dashboard.agent.nodes import (
    _is_first_turn,
    build_analyze_node,
    build_correlate_node,
    build_ingest_node,
    build_predict_node,
    build_respond_node,
    route_after_analyze,
    route_after_predict,
)
from log_dashboard.agent.tools import build_tools
from log_dashboard.config import get_settings


def _state(messages=None, **overrides):
    base: dict = {
        "messages": list(messages or []),
        "session_id": "sess-1",
        "jwt_sub": "admin",
        "citations": [],
        "dry_run": True,
        "tool_budget_remaining": 4,
        "tool_budget_exhausted": False,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_ingest_resets_budget_and_dry_run_flag() -> None:
    settings = get_settings()
    state = _state(
        messages=[HumanMessage(content="hi", id="m-1")],
        tool_budget_remaining=0,
        dry_run=False,
        tool_budget_exhausted=True,
    )
    node = build_ingest_node(settings)
    update = await node(state)
    assert update["tool_budget_remaining"] == settings.llm_max_tool_calls_per_request
    assert update["dry_run"] is True  # Settings default
    assert update["tool_budget_exhausted"] is False
    assert update["citations"] == []


@pytest.mark.asyncio
async def test_ingest_sanitises_user_message_when_dirty() -> None:
    settings = get_settings()
    dirty = "investigate this token: Bearer eyJabcdefghijklmnopqrstuvwxyz"
    state = _state(messages=[HumanMessage(content=dirty, id="m-1")])
    update = await build_ingest_node(settings)(state)
    assert "messages" in update
    new_msg = update["messages"][0]
    assert "[REDACTED]" in new_msg.content
    assert "eyJabcdefghijklmnopqrstuvwxyz" not in new_msg.content
    assert new_msg.id == "m-1"  # Reducer treats same-id as update, not append


@pytest.mark.asyncio
async def test_ingest_no_op_when_message_clean() -> None:
    settings = get_settings()
    state = _state(messages=[HumanMessage(content="what is wrong?", id="m-1")])
    update = await build_ingest_node(settings)(state)
    # No `messages` key in update means MessagesState reducer leaves the
    # existing message untouched — avoids spuriously appending a dup.
    assert "messages" not in update


@pytest.mark.asyncio
async def test_analyze_calls_llm_with_tools_bound(fake_vectorstore) -> None:
    settings = get_settings()
    tools = build_tools(settings, fake_vectorstore)
    state = _state(messages=[HumanMessage(content="what is wrong?")])
    update = await build_analyze_node(settings, tools)(state)
    assert "messages" in update
    last = update["messages"][-1]
    # Dry-run model emits one query_logs tool call on first invocation.
    assert isinstance(last, AIMessage)
    assert last.tool_calls
    assert last.tool_calls[0]["name"] == "query_logs"


@pytest.mark.asyncio
async def test_correlate_executes_tools_and_decrements_budget(fake_vectorstore) -> None:
    settings = get_settings()
    tools = build_tools(settings, fake_vectorstore)
    # Construct a state that already has the LLM's tool_call request.
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "query_logs",
                "args": {"query": "errors", "top_k": 3},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )
    state = _state(
        messages=[HumanMessage(content="why?"), ai],
        tool_budget_remaining=4,
    )
    update = await build_correlate_node(tools)(state)
    assert update["tool_budget_remaining"] == 3
    assert update["tool_budget_exhausted"] is False
    # ToolNode appended a ToolMessage with the tool result.
    assert any(isinstance(m, ToolMessage) for m in update["messages"])


@pytest.mark.asyncio
async def test_correlate_flips_exhausted_when_budget_hits_zero(fake_vectorstore) -> None:
    settings = get_settings()
    tools = build_tools(settings, fake_vectorstore)
    ai = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "query_logs",
                "args": {"query": "errors"},
                "id": "call_1",
                "type": "tool_call",
            }
        ],
    )
    state = _state(messages=[HumanMessage(content="why?"), ai], tool_budget_remaining=1)
    update = await build_correlate_node(tools)(state)
    assert update["tool_budget_remaining"] == 0
    assert update["tool_budget_exhausted"] is True


@pytest.mark.asyncio
async def test_predict_after_tool_returns_canned_final(fake_vectorstore) -> None:
    """With a ToolMessage in state, the dry-run model emits the canned final
    answer (no tool_calls), so `route_after_predict` will route to respond."""
    settings = get_settings()
    tools = build_tools(settings, fake_vectorstore)
    state = _state(
        messages=[
            HumanMessage(content="why?"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "query_logs",
                        "args": {},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            ),
            ToolMessage(content='{"results": []}', tool_call_id="c1", name="query_logs"),
        ]
    )
    update = await build_predict_node(settings, tools)(state)
    last = update["messages"][-1]
    assert isinstance(last, AIMessage)
    assert not last.tool_calls
    assert "DRY_RUN" in last.content


@pytest.mark.asyncio
async def test_respond_extracts_citations_from_tool_messages(fake_vectorstore) -> None:
    """`respond` walks the tool-message history and surfaces query_logs results
    as `CitedLogEntry` instances on `state["citations"]`."""
    # Add one doc to the vectorstore so the tool returns a result we can cite.
    from langchain_core.documents import Document

    fake_vectorstore.add_documents(
        documents=[
            Document(
                page_content="fnol error",
                metadata={
                    "id": "fnol:test-1",
                    "app": "fnol",
                    "level": "ERROR",
                    "event": "request_failed",
                    "timestamp_iso": "2026-06-05T10:00:00+00:00",
                    "raw": "ERROR fnol request_failed",
                },
            )
        ],
        ids=["fnol:test-1"],
    )
    settings = get_settings()
    tools = build_tools(settings, fake_vectorstore)
    # Drive analyze + correlate + respond directly.
    state = _state(messages=[HumanMessage(content="why is fnol failing?")])
    a = await build_analyze_node(settings, tools)(state)
    state["messages"].extend(a["messages"])
    c = await build_correlate_node(tools)(state)
    state["messages"].extend(c["messages"])
    state["tool_budget_remaining"] = c["tool_budget_remaining"]
    state["tool_budget_exhausted"] = c["tool_budget_exhausted"]
    r = await build_respond_node()(state)
    assert len(r["citations"]) >= 1
    cite = r["citations"][0]
    assert cite.app == "fnol"
    assert cite.level.value == "ERROR"


def test_route_after_analyze_to_correlate() -> None:
    state = _state(
        messages=[
            HumanMessage(content="hi"),
            AIMessage(
                content="",
                tool_calls=[{"name": "x", "args": {}, "id": "c1", "type": "tool_call"}],
            ),
        ]
    )
    assert route_after_analyze(state) == "correlate"


def test_route_after_analyze_to_respond_when_no_tool_calls() -> None:
    state = _state(messages=[HumanMessage(content="hi"), AIMessage(content="answer")])
    assert route_after_analyze(state) == "respond"


def test_route_after_predict_respects_budget() -> None:
    ai_with_tools = AIMessage(
        content="",
        tool_calls=[{"name": "x", "args": {}, "id": "c1", "type": "tool_call"}],
    )
    # Budget remaining + tool_calls → correlate
    state_ok = _state(messages=[ai_with_tools], tool_budget_remaining=2)
    assert route_after_predict(state_ok) == "correlate"
    # Budget exhausted → respond even with tool_calls
    state_exhausted = _state(messages=[ai_with_tools], tool_budget_remaining=0)
    assert route_after_predict(state_exhausted) == "respond"
    # No tool_calls → respond regardless
    state_done = _state(messages=[AIMessage(content="done")], tool_budget_remaining=4)
    assert route_after_predict(state_done) == "respond"


# ---------------------------------------------------------------------------
# Phase 8 / ADR-017 — baseline-aware SystemMessage injection at analyze
# ---------------------------------------------------------------------------


def test_is_first_turn_true_for_human_only() -> None:
    assert _is_first_turn([HumanMessage(content="hi")]) is True


def test_is_first_turn_true_for_multiple_human_messages() -> None:
    """Two HumanMessages in a row (e.g., user replayed before any LLM
    activity) still counts as 'first turn' for SystemMessage injection."""
    messages = [HumanMessage(content="first"), HumanMessage(content="second")]
    assert _is_first_turn(messages) is True


def test_is_first_turn_false_when_ai_message_present() -> None:
    messages = [HumanMessage(content="hi"), AIMessage(content="hello")]
    assert _is_first_turn(messages) is False


def test_is_first_turn_false_when_tool_message_present() -> None:
    messages = [
        HumanMessage(content="hi"),
        ToolMessage(content="{}", tool_call_id="x"),
    ]
    assert _is_first_turn(messages) is False


def test_is_first_turn_true_when_empty() -> None:
    """Edge case — no messages at all. `_is_first_turn` returns True
    (vacuously: no AIMessage/ToolMessage exists). `analyze_node` never
    reaches that branch in practice because `ingest_node` runs first
    and always finds at least one HumanMessage. Documents the predicate's
    contract; if a future caller of `analyze_node` could pass an empty
    list, change this test + the predicate together to defend against
    SystemMessage injection on an empty prompt."""
    assert _is_first_turn([]) is True


class _RecordingChatModel:
    """Drop-in for `_DryRunChatModel` that captures the message list it
    receives. Provider-agnostic — we don't subclass BaseChatModel because
    we never feed this into LangGraph's real runtime; the analyze node
    just calls `model.ainvoke(messages)`.
    """

    def __init__(self) -> None:
        self.calls: list[list] = []

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002 — match real signature
        return self

    async def ainvoke(self, messages, *args, **kwargs):  # noqa: ARG002
        self.calls.append(list(messages))
        return AIMessage(content="ok")


@pytest.mark.asyncio
async def test_analyze_prepends_system_message_on_first_turn(monkeypatch) -> None:
    """First analyze call of a session — state.messages contains only a
    HumanMessage. The baseline-aware SystemMessage must be prepended to
    the message list passed to `model.ainvoke`."""
    recorder = _RecordingChatModel()
    from log_dashboard.agent import nodes as nodes_module

    monkeypatch.setattr(nodes_module, "build_chat_model", lambda _settings: recorder)

    settings = get_settings()
    analyze = build_analyze_node(settings, tools=[])
    await analyze(_state(messages=[HumanMessage(content="is this normal?")]))

    assert len(recorder.calls) == 1
    invoked = recorder.calls[0]
    assert isinstance(
        invoked[0], SystemMessage
    ), f"first message should be SystemMessage; got {type(invoked[0]).__name__}"
    # The injected prompt is the baseline-aware directive.
    assert "baseline" in invoked[0].content.lower()
    # The original HumanMessage follows the SystemMessage.
    assert isinstance(invoked[1], HumanMessage)
    assert invoked[1].content == "is this normal?"


@pytest.mark.asyncio
async def test_analyze_does_not_prepend_system_message_after_tool_use(monkeypatch) -> None:
    """Subsequent analyze calls (after the first tool round-trip) must
    NOT inject the SystemMessage. Otherwise the directive would re-fire
    every turn and burn ~220 tokens against the per-request cap."""
    recorder = _RecordingChatModel()
    from log_dashboard.agent import nodes as nodes_module

    monkeypatch.setattr(nodes_module, "build_chat_model", lambda _settings: recorder)

    settings = get_settings()
    analyze = build_analyze_node(settings, tools=[])
    state = _state(
        messages=[
            HumanMessage(content="follow-up"),
            AIMessage(
                content="",
                tool_calls=[{"name": "query_logs", "args": {"query": "x"}, "id": "c1"}],
            ),
            ToolMessage(content='{"results":[]}', tool_call_id="c1", name="query_logs"),
        ]
    )
    await analyze(state)

    assert len(recorder.calls) == 1
    invoked = recorder.calls[0]
    # First message must NOT be a SystemMessage — the tool round already
    # established context.
    assert not isinstance(
        invoked[0], SystemMessage
    ), f"SystemMessage should NOT be injected after tool use; got {type(invoked[0]).__name__}"
    # The original 3 messages should pass through unchanged.
    assert len(invoked) == 3
