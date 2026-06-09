"""Regression guard for the LLM factory's timeout plumbing.

PR #59 burned ~3 round-trips because `ChatOllama(timeout=N)` is silently
absorbed by pydantic `extra="allow"` — the kwarg never reaches httpx and
every cold-start chat call false-fails on the default httpx 5-second
read timeout. The supported path is `client_kwargs={"timeout": N}`,
which langchain-ollama forwards into both sync and async client
constructors.

This test exists so the NEXT silent-absorption gotcha surfaces as a
failing test rather than a 502 in production. If a refactor drops
`client_kwargs`, renames it, or stops forwarding `settings.llm_timeout_seconds`
into it, the assertion fails before the change ships.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama

from log_dashboard.agent.llm import _build_real_model, _DryRunChatModel, build_chat_model
from log_dashboard.config import Settings


def test_build_real_model_forwards_timeout_via_client_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DASHBOARD_LLM_DRY_RUN", "false")
    monkeypatch.setenv("DASHBOARD_LLM_TIMEOUT_SECONDS", "47")

    settings = Settings()  # type: ignore[call-arg]
    model = _build_real_model(settings)

    assert isinstance(model, ChatOllama)
    assert model.client_kwargs == {"timeout": 47}


def test_build_chat_model_dry_run_returns_fake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run gate keeps the factory from constructing ChatOllama at all,
    so `client_kwargs` plumbing is irrelevant in that branch."""
    monkeypatch.setenv("DASHBOARD_LLM_DRY_RUN", "true")
    settings = Settings()  # type: ignore[call-arg]
    model = build_chat_model(settings)
    assert isinstance(model, _DryRunChatModel)


# ---------------------------------------------------------------------------
# Direct unit tests for `_DryRunChatModel._respond()` — exercise the
# state-machine without going through the full graph. Integration tests
# (`test_agent_nodes.py`, `test_chat_route_dry_run.py`) cover the graph end
# of the story; these cases pin the model's per-call decision logic.
# ---------------------------------------------------------------------------


def test_dry_run_respond_first_turn_emits_tool_call() -> None:
    """With no ToolMessage yet seen, the fake must emit one `query_logs`
    tool call. `analyze` produces this; `correlate` dispatches it."""
    messages = [HumanMessage(content="what is wrong with fnol?")]
    out = _DryRunChatModel._respond(messages)
    assert out.content == ""
    assert len(out.tool_calls) == 1
    assert out.tool_calls[0]["name"] == "query_logs"
    assert "query" in out.tool_calls[0]["args"]


def test_dry_run_respond_after_tool_message_emits_final_answer() -> None:
    """Once a ToolMessage is present in the history, the fake must emit
    the canned final answer with no tool calls. `predict` produces this;
    `respond` finalises."""
    messages = [
        HumanMessage(content="what is wrong?"),
        AIMessage(content="", tool_calls=[{"name": "query_logs", "args": {}, "id": "1"}]),
        ToolMessage(content="3 hits", tool_call_id="1"),
    ]
    out = _DryRunChatModel._respond(messages)
    assert out.content.startswith("DRY_RUN")
    assert out.tool_calls == []


def test_dry_run_respond_with_only_system_message_still_emits_tool_call() -> None:
    """The ingest node prepends a SystemMessage on first turn; the fake
    must NOT confuse a SystemMessage for a ToolMessage and skip straight
    to the canned answer. Without this guard the graph would never
    exercise `correlate`."""
    messages = [
        SystemMessage(content="you are a log analyst"),
        HumanMessage(content="check fnol"),
    ]
    out = _DryRunChatModel._respond(messages)
    assert out.content == ""
    assert len(out.tool_calls) == 1


def test_dry_run_respond_with_empty_messages_still_emits_tool_call() -> None:
    """Empty list is a defensive case — should not crash, should not
    short-circuit to the canned answer. Acts like the first turn."""
    out = _DryRunChatModel._respond([])
    assert out.content == ""
    assert len(out.tool_calls) == 1


def test_dry_run_bind_tools_returns_self() -> None:
    """`bind_tools` must return self so the graph's chained
    `model.bind_tools(...)` works without branching on dry-run."""
    model = _DryRunChatModel()
    bound = model.bind_tools([])
    assert bound is model


def test_dry_run_llm_type_marks_provider_for_langsmith() -> None:
    """`_llm_type` is surfaced in LangSmith traces. The string is the
    operator's signal that a trace came from the fake, not real Ollama."""
    assert _DryRunChatModel()._llm_type == "dry-run-fake"
