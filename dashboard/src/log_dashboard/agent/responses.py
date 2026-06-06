"""Agent-output adapters shared by `/api/chat` and `/api/errors/{id}`.

Both routers turn an AgentState dict into an API response and both apply the
same token-cap rejection on the way in. Holding these helpers here keeps the
routers thin and prevents the two surfaces from drifting on output shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage

from ..credentials import sanitize_log_raw
from ..schemas import Citation


def extract_answer(state: dict[str, Any]) -> str:
    """Pull the final AIMessage content and sanitise it.

    Inputs entering the graph are already sanitised in `ingest_node`, and
    tool-returned `raw` fields are sanitised in `query_logs`, so a clean LLM
    cannot generate a secret it never saw. The sanitiser runs again here as
    defence-in-depth — matches the ADR-015 §8 promise that the response body
    never carries a credential.
    """
    messages = state.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = msg.content
            if isinstance(content, str):
                return sanitize_log_raw(content)
            if isinstance(content, list):
                return sanitize_log_raw("".join(str(b) for b in content))
            return sanitize_log_raw(str(content))
    return ""


def extract_citations(state: dict[str, Any]) -> list[Citation]:
    """Re-shape the agent's CitedLogEntry list into the API Citation schema.

    Both schemas mirror a subset of `LogEntry`; the difference is that
    `timestamp` is an ISO string in CitedLogEntry (tool-message-safe) and a
    `datetime` in Citation (Pydantic serialises it back to ISO on the wire).
    """
    citations: list[Citation] = []
    for entry in state.get("citations") or []:
        try:
            ts_raw = entry.timestamp
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else None
        except (ValueError, AttributeError):
            ts = None
        if ts is None:
            continue
        citations.append(
            Citation(
                id=entry.id,
                timestamp=ts,
                level=entry.level,
                app=entry.app,
                event=entry.event,
                raw=sanitize_log_raw(entry.raw),
                score=entry.score,
            )
        )
    return citations


def is_openai_api_error(exc: BaseException) -> bool:
    """Lazy-import isinstance check so dry-run installs without `openai` work."""
    try:
        from openai import APIError
    except ImportError:
        return False
    return isinstance(exc, APIError)


def count_tokens(text: str, model: str) -> int:
    """Tiktoken count for `text` against `model`'s encoding.

    Falls back to `o200k_base` (gpt-4o family) for unknown model strings so
    we still get a usable estimate.
    """
    import tiktoken

    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("o200k_base")
    return len(enc.encode(text))
