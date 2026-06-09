"""Agent-output adapters shared by `/api/chat` and `/api/errors/{id}`.

Both routers turn an AgentState dict into an API response and both apply the
same token-cap rejection on the way in. Holding these helpers here keeps the
routers thin and prevents the two surfaces from drifting on output shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from langchain_core.messages import AIMessage

from ..credentials import sanitize_log_raw
from ..schemas import Citation

# Exception types that surface as a 502 "upstream LLM unavailable" via
# `is_llm_api_error`. Hoisted to module scope so a future maintainer can
# extend the set in one place — and so the rationale (these are the
# specific failure modes ChatOllama actually raises, NOT the bare
# `httpx.HTTPError` base) lives next to the list.
#
# Previously this catch was `httpx.HTTPError`, the base class. That would
# misclassify any future non-LLM httpx caller in the graph (e.g., a tool
# that fetches an upstream URL) as a 502. The narrowed set keeps the
# 502-mapping scoped to actual LLM-transport failures.
_LLM_API_ERROR_TYPES: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.HTTPStatusError,
    # Python 3.11+ — `asyncio.TimeoutError` is the SAME class object as
    # the builtin `TimeoutError`. Including only the builtin covers
    # both names (`isinstance(asyncio.TimeoutError(), TimeoutError) is
    # True`). Adding `asyncio.TimeoutError` here would create a silent
    # duplicate.
    TimeoutError,
    ConnectionError,
)


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


def is_llm_api_error(exc: BaseException) -> bool:
    """True for upstream LLM transport failures the router should surface as 502.

    Phase 8 / ADR-017 — broadened from the Phase 7 `openai.APIError` check
    to cover the failure modes the local Ollama client emits. `ChatOllama`
    is built on `httpx`, so connection errors and timeouts come through as
    specific `httpx.HTTPError` subclasses (see `_LLM_API_ERROR_TYPES`).
    The underlying `ollama` python client also raises `ResponseError` on
    non-200 replies; we match it by module + class name to avoid an
    import-time dependency.
    """
    if isinstance(exc, _LLM_API_ERROR_TYPES):
        return True
    # Match the `ollama` client's `ResponseError` by module + class name
    # without an import. Tightened to `module == "ollama"` or
    # `startswith("ollama.")` so a third-party `ollama_utils.ResponseError`
    # wouldn't false-positive.
    cls = type(exc)
    module = getattr(cls, "__module__", "") or ""
    if (module == "ollama" or module.startswith("ollama.")) and cls.__name__ == "ResponseError":
        return True
    return False


def count_tokens(text: str) -> int:
    """Estimate token count via the `len(text) // 4` character-count heuristic.

    Phase 8 / ADR-017 drops `tiktoken` (OpenAI-specific) in favor of a
    cheap heuristic that's good enough for an in-graph safety bound on
    input size. The number is a coarse proxy, not a billing meter — the
    bound exists to keep one absurdly large request from filling the
    context window, not to track spend.
    """
    return len(text) // 4
