"""Graph nodes — ingest, analyze, correlate, predict, respond.

Topology (from `.claude/rules/dashboard.md:24` + ADR-015):

    START → ingest → analyze → (tool_calls? correlate → predict → ... : respond) → END

`analyze` and `predict` are functionally identical (LLM call with tools
bound). They are kept as separate nodes for the rule's 5-name palette;
both delegate to `_invoke_llm_with_tools`.

`correlate` dispatches tool calls manually rather than wrapping
`langgraph.prebuilt.ToolNode`. ToolNode requires LangGraph's internal
runtime context (only injected when invoked through a compiled graph), so
unit tests that exercise the node directly would need elaborate fixtures.
Manual dispatch is ~20 lines, has no hidden state, and lets us decrement
the per-request tool budget atomically with the dispatch.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ..credentials import sanitize_user_input
from ..logging_setup import get_logger
from .llm import build_chat_model
from .state import AgentState, CitedLogEntry

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from ..config import Settings

log = get_logger("agent.nodes")


def build_ingest_node(settings: Settings):
    """Reset per-request budget + dry-run flag + sanitise the latest user message.

    `MessagesState`'s reducer `add_messages` appends incoming messages, so the
    new user `HumanMessage` from this request is the LAST entry in
    `state["messages"]` when `ingest` runs.
    """

    async def ingest_node(state: AgentState) -> dict[str, Any]:
        # Find the most recent HumanMessage (the new request).
        last_human_idx = _last_index_of(state["messages"], HumanMessage)
        updates: dict[str, Any] = {
            "dry_run": settings.dashboard_llm_dry_run,
            "tool_budget_remaining": settings.llm_max_tool_calls_per_request,
            "tool_budget_exhausted": False,
            "citations": [],
        }
        if last_human_idx is None:
            return updates

        last_human = state["messages"][last_human_idx]
        raw_text = last_human.content if isinstance(last_human.content, str) else ""
        sanitised = sanitize_user_input(raw_text)
        if sanitised == raw_text:
            # No change — common case, avoid spending tokens on a no-op message edit.
            return updates

        # Replace the message in-place. MessagesState's add_messages reducer
        # treats messages with the same .id as updates rather than appends.
        sanitised_msg = HumanMessage(content=sanitised, id=last_human.id)
        return {**updates, "messages": [sanitised_msg]}

    return ingest_node


def build_analyze_node(settings: Settings, tools: list[BaseTool]):
    """First LLM call — model decides whether to call tools or answer directly."""

    async def analyze_node(state: AgentState) -> dict[str, Any]:
        return await _invoke_llm_with_tools(settings, tools, state)

    return analyze_node


def build_correlate_node(tools: list[BaseTool]):
    """Run requested tools + decrement the per-request budget.

    Dispatches each tool call on the last AIMessage manually. Each pass
    through `correlate` counts as ONE tool round regardless of how many
    parallel tool calls the LLM batched — the cost bound is on round-trips.

    Errors raised inside a tool are caught and surfaced to the LLM as
    `{"tool_error": "..."}` so the agent can self-correct instead of the
    graph crashing.
    """
    tool_by_name = {t.name: t for t in tools}

    async def correlate_node(state: AgentState) -> dict[str, Any]:
        last = state["messages"][-1] if state["messages"] else None
        tool_calls = list(getattr(last, "tool_calls", None) or [])
        new_messages: list[ToolMessage] = []
        for call in tool_calls:
            name = call.get("name", "")
            args = call.get("args", {}) or {}
            call_id = call.get("id", "")
            tool = tool_by_name.get(name)
            if tool is None:
                new_messages.append(
                    ToolMessage(
                        content=json.dumps({"tool_error": f"unknown_tool: {name}"}),
                        tool_call_id=call_id,
                        name=name,
                    )
                )
                continue
            try:
                # Tools are sync — run off the event loop so a slow tool
                # (Chroma similarity search hitting disk) doesn't block.
                result = await asyncio.to_thread(tool.invoke, args)
            except Exception as exc:  # noqa: BLE001 — surface as tool_error, never crash
                log.warning(
                    "agent_tool_invocation_failed",
                    tool=name,
                    error_class=type(exc).__name__,
                )
                result = {"tool_error": "tool_invocation_failed"}
            content = result if isinstance(result, str) else json.dumps(result)
            new_messages.append(ToolMessage(content=content, tool_call_id=call_id, name=name))
        remaining = max(0, int(state.get("tool_budget_remaining", 0)) - 1)
        return {
            "messages": new_messages,
            "tool_budget_remaining": remaining,
            "tool_budget_exhausted": remaining == 0,
        }

    return correlate_node


def build_predict_node(settings: Settings, tools: list[BaseTool]):
    """Post-tool LLM call — model reflects on tool output, may request more.

    Implementation is identical to `analyze_node` (same LLM-with-tools call).
    Separated as a node for the rule's 5-name palette + so future PR 4c work
    can plug a different prompt/middleware here without touching `analyze`.
    """

    async def predict_node(state: AgentState) -> dict[str, Any]:
        return await _invoke_llm_with_tools(settings, tools, state)

    return predict_node


def build_respond_node():
    """Terminal node — extract citations from prior ToolMessages.

    The LLM's final AIMessage (no tool_calls) is already in `state["messages"]`
    from the last `analyze` or `predict` call; `respond` just harvests the
    cited log entries the agent saw and stashes them in `state["citations"]`
    so the router can surface them to the client.
    """

    async def respond_node(state: AgentState) -> dict[str, Any]:
        citations = _extract_citations(state["messages"])
        return {"citations": citations}

    return respond_node


# --- Conditional-edge routers ----------------------------------------------


def route_after_analyze(state: AgentState) -> str:
    """Standard agent-loop router after the FIRST LLM call.

    If the LLM emitted tool calls, go to `correlate`. Otherwise, the LLM
    answered directly — go straight to `respond`.
    """
    last = state["messages"][-1] if state["messages"] else None
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "correlate"
    return "respond"


def route_after_predict(state: AgentState) -> str:
    """Router after the POST-TOOL LLM call.

    If the LLM asked for more tools AND we still have budget, loop back
    through `correlate`. Otherwise — either the LLM is done, or the budget
    is exhausted — go to `respond`. The budget-exhaustion flag is already
    set on state by `correlate_node`, so `respond` can surface it.
    """
    last = state["messages"][-1] if state["messages"] else None
    has_tool_calls = isinstance(last, AIMessage) and bool(getattr(last, "tool_calls", None))
    remaining = int(state.get("tool_budget_remaining", 0))
    if has_tool_calls and remaining > 0:
        return "correlate"
    return "respond"


# --- Helpers ---------------------------------------------------------------


async def _invoke_llm_with_tools(
    settings: Settings, tools: list[BaseTool], state: AgentState
) -> dict[str, Any]:
    """Shared LLM call body used by both `analyze` and `predict`."""
    model = build_chat_model(settings).bind_tools(tools)
    response = await model.ainvoke(state["messages"])
    return {"messages": [response]}


def _last_index_of(messages: list, cls: type) -> int | None:
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], cls):
            return i
    return None


def _extract_citations(messages: list) -> list[CitedLogEntry]:
    """Walk the tool-message history and pull every `query_logs` result.

    Each `ToolMessage` produced by ToolNode carries `name="query_logs"` and
    `content` that is either a JSON-encoded string or already-parsed dict
    (depends on the LangChain version). We accept both.
    """
    out: list[CitedLogEntry] = []
    seen_ids: set[str] = set()
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        if getattr(msg, "name", None) != "query_logs":
            continue
        payload = _parse_tool_content(msg.content)
        results = payload.get("results") or []
        for raw_entry in results:
            try:
                entry = CitedLogEntry.model_validate(raw_entry)
            except Exception as exc:  # noqa: BLE001 — never crash respond on a malformed entry
                log.warning(
                    "agent_citation_parse_failed",
                    error_class=type(exc).__name__,
                )
                continue
            if entry.id in seen_ids:
                continue
            seen_ids.add(entry.id)
            out.append(entry)
    return out


def _parse_tool_content(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}
