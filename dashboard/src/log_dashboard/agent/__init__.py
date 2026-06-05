"""LangGraph agent — Phase 7e (PR 4a).

Five-node graph (ingest → analyze → correlate → predict → respond) that
queries Chroma + app status to answer operator questions over chat.

Exports:
- `build_agent_graph(settings, vectorstore, checkpointer)` — compile-time entry
- `AgentState` — extended `MessagesState` carrying session id, citations, budget
- `CitedLogEntry` — the typed shape `query_logs` returns
"""

from .graph import build_agent_graph
from .state import AgentState, CitedLogEntry

__all__ = ["build_agent_graph", "AgentState", "CitedLogEntry"]
