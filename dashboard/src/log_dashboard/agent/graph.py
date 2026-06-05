"""Compile the 5-node StateGraph: ingest → analyze → correlate → predict → respond.

Built once at lifespan with the live `vectorstore` + `checkpointer` injected;
attached to `app.state.agent_graph` and reused across every `/api/chat` call.

The 5 node names match `.claude/rules/dashboard.md:24` exactly. Functional
mapping:

* `ingest` — request hygiene (sanitise user input, reset per-request budget)
* `analyze` — first LLM call; routes to `correlate` if tools requested else `respond`
* `correlate` — ToolNode wrapper that executes tools + decrements budget
* `predict` — post-tool LLM call; loops back to `correlate` if more tools AND budget>0
* `respond` — terminal node; harvests citations from ToolMessages
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from .nodes import (
    build_analyze_node,
    build_correlate_node,
    build_ingest_node,
    build_predict_node,
    build_respond_node,
    route_after_analyze,
    route_after_predict,
)
from .state import AgentState
from .tools import build_tools

if TYPE_CHECKING:
    from langchain_chroma import Chroma
    from langgraph.checkpoint.memory import InMemorySaver

    from ..config import Settings


def build_agent_graph(
    settings: Settings,
    vectorstore: Chroma | None,
    checkpointer: InMemorySaver,
):
    """Compile and return the LangGraph chat agent.

    `vectorstore=None` is permitted — degraded mode when no OpenAI key is
    set. The `query_logs` tool degrades gracefully (returns
    `{tool_error: "vectorstore_unavailable"}`) so the graph still runs.

    The checkpointer MUST be an `InMemorySaver` (or any `BaseCheckpointSaver`
    that supports thread-scoped persistence). Callers should pass the one
    they constructed for `app.state.session_index` so eviction stays in sync.
    """
    tools = build_tools(settings, vectorstore)

    ingest_node = build_ingest_node(settings)
    analyze_node = build_analyze_node(settings, tools)
    correlate_node = build_correlate_node(tools)
    predict_node = build_predict_node(settings, tools)
    respond_node = build_respond_node()

    builder = StateGraph(AgentState)
    builder.add_node("ingest", ingest_node)
    builder.add_node("analyze", analyze_node)
    builder.add_node("correlate", correlate_node)
    builder.add_node("predict", predict_node)
    builder.add_node("respond", respond_node)

    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "analyze")
    builder.add_conditional_edges(
        "analyze",
        route_after_analyze,
        {"correlate": "correlate", "respond": "respond"},
    )
    builder.add_edge("correlate", "predict")
    builder.add_conditional_edges(
        "predict",
        route_after_predict,
        {"correlate": "correlate", "respond": "respond"},
    )
    builder.add_edge("respond", END)

    return builder.compile(checkpointer=checkpointer)
