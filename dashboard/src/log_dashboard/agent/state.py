"""LangGraph state schema + the typed shape `query_logs` returns.

`AgentState` extends `MessagesState` with five custom keys that ride alongside
the canonical `messages: list[BaseMessage]`. The `messages` reducer is the
default `add_messages` provided by `MessagesState` — node return values
either replace or append per LangGraph's reducer contract.
"""

from __future__ import annotations

from langgraph.graph import MessagesState
from pydantic import BaseModel

from ..schemas import LogLevel


class CitedLogEntry(BaseModel):
    """A single log line surfaced by `query_logs`.

    Constructed inside the tool from a Chroma `Document`. The `raw` field has
    already been passed through `credentials.sanitize_log_raw` before the
    `CitedLogEntry` is returned to the LLM, so it is safe to embed in tool
    output and chat responses.
    """

    id: str
    timestamp: str  # ISO 8601 — keep as string so it round-trips through ToolMessage JSON
    level: LogLevel
    app: str
    event: str
    raw: str
    score: float


class AgentState(MessagesState):
    """LangGraph state for the chat agent.

    Inherits `messages: Annotated[list[AnyMessage], add_messages]` from
    `MessagesState`. The custom keys below ride alongside.

    `tool_budget_remaining` is decremented in `correlate` when tool calls
    are dispatched. When it hits 0, the conditional edge from `predict`
    short-circuits to `respond` even if the LLM asked for more tools —
    cost-bounding.
    """

    session_id: str
    jwt_sub: str
    citations: list[CitedLogEntry]
    dry_run: bool
    tool_budget_remaining: int
    tool_budget_exhausted: bool
