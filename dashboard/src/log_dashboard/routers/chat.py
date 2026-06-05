"""POST /api/chat — LangGraph agent invocation.

Flow per request:
1. Validate body (ChatRequest); 422 if `streaming=true` (forward-compat reservation)
2. Sanitise the user message (defence-in-depth — `ingest_node` also runs the
   sanitiser, but doing it here too means the token-count + log line in this
   router never see the raw secret)
3. Token-count via tiktoken against `gpt-4o`'s `o200k_base` encoding;
   413 if over `settings.llm_max_input_tokens_per_request`
4. Mint or reuse `session_id` → derive LangGraph `thread_id`
5. Touch the SessionIndex (LRU eviction if over cap)
6. `await graph.ainvoke(state, config={'configurable': {'thread_id': ...},
   'metadata': {...}})` — metadata flows to LangSmith for filtering
7. Catch `openai.APIError` → 502
8. Build ChatResponse: final AIMessage content + citations + dry_run +
   tool_budget_exhausted + session_id
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from langchain_core.messages import AIMessage, HumanMessage

from ..agent.sessions import new_session_id, thread_id_for
from ..auth.jwt import get_current_admin
from ..config import Settings, get_settings
from ..credentials import sanitize_log_raw, sanitize_user_input
from ..logging_setup import get_logger
from ..schemas import ChatRequest, ChatResponse, Citation

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from ..agent.sessions import SessionIndex

router = APIRouter(tags=["chat"])
log = get_logger("chat")

# Truncate user message previews in log lines so a paragraph-long question
# doesn't balloon the log file. The query itself is admin input, not a
# credential, but bounded log lines are easier to consume downstream.
_LOG_PREVIEW_LIMIT = 200


def _get_graph(request: Request) -> CompiledStateGraph:
    graph = getattr(request.app.state, "agent_graph", None)
    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="agent graph not initialised",
        )
    return graph


def _get_session_index(request: Request) -> SessionIndex:
    idx = getattr(request.app.state, "session_index", None)
    if idx is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="session index not initialised",
        )
    return idx


def _count_tokens(text: str, model: str) -> int:
    """Tiktoken count for `text` against `model`'s encoding.

    Falls back to `o200k_base` (gpt-4o family) for unknown model strings so
    we still get a usable estimate. Wrapped here so the router doesn't need
    to know about tiktoken's specifics.
    """
    import tiktoken

    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("o200k_base")
    return len(enc.encode(text))


@router.post("/chat", response_model=ChatResponse)
async def post_chat(
    body: ChatRequest,
    request: Request,
    payload: dict[str, Any] = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    # Forward-compatibility reservation — streaming arrives in PR 4b. Rejected
    # here rather than in a `model_validator` so the rejection doesn't drag a
    # raw `ValueError` instance into the validation handler's `ctx` field.
    if body.streaming:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="streaming responses are not supported in PR 4a — set streaming=false",
        )

    # Sanitise the message BEFORE token counting + logging. Defence-in-depth:
    # `ingest_node` runs the same sanitiser, but this router never sees the
    # raw secret in its preview log line.
    message_sanitised = sanitize_user_input(body.message)

    # Cost guard. Counted against the chat model's encoding so we reject
    # before the LangGraph dispatcher spends anything.
    token_count = _count_tokens(message_sanitised, settings.openai_chat_model)
    if token_count > settings.llm_max_input_tokens_per_request:
        log.info(
            "chat_rejected_token_cap",
            tokens=token_count,
            cap=settings.llm_max_input_tokens_per_request,
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"message exceeds input token cap "
                f"({token_count} > {settings.llm_max_input_tokens_per_request})"
            ),
        )

    jwt_sub = str(payload.get("sub") or "admin")
    session_id = body.session_id or new_session_id()
    thread_id = thread_id_for(jwt_sub, session_id)
    await _get_session_index(request).touch(thread_id)

    graph = _get_graph(request)

    config = {
        "configurable": {"thread_id": thread_id},
        "metadata": {
            "session_id": session_id,
            "jwt_sub": jwt_sub,
            "dry_run": settings.dashboard_llm_dry_run,
        },
    }

    log.info(
        "chat_started",
        session_id=session_id,
        dry_run=settings.dashboard_llm_dry_run,
        message_preview=_truncate(message_sanitised),
        tokens=token_count,
    )

    initial_state: dict[str, Any] = {
        "messages": [HumanMessage(content=message_sanitised)],
        "session_id": session_id,
        "jwt_sub": jwt_sub,
        # `ingest_node` overrides these on entry, but we initialise them
        # explicitly so checkpoint restoration on a new session has sane
        # defaults.
        "citations": [],
        "dry_run": settings.dashboard_llm_dry_run,
        "tool_budget_remaining": settings.llm_max_tool_calls_per_request,
        "tool_budget_exhausted": False,
    }

    try:
        result = await graph.ainvoke(initial_state, config=config)
    except Exception as exc:
        # Surface OpenAI / upstream LLM failures as 502; everything else
        # (programming errors, schema issues) bubbles to the global 500
        # handler. We import openai lazily so dry-run installs don't pay
        # the import cost.
        if _is_openai_api_error(exc):
            log.warning(
                "chat_upstream_failure",
                session_id=session_id,
                error_class=type(exc).__name__,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="upstream LLM unavailable — try again shortly",
            ) from exc
        raise

    answer = _extract_answer(result)
    citations = _extract_citations(result)
    dry_run = bool(result.get("dry_run", settings.dashboard_llm_dry_run))
    tool_budget_exhausted = bool(result.get("tool_budget_exhausted", False))

    log.info(
        "chat_complete",
        session_id=session_id,
        dry_run=dry_run,
        citation_count=len(citations),
        tool_budget_exhausted=tool_budget_exhausted,
    )

    return ChatResponse(
        answer=answer,
        citations=citations,
        session_id=session_id,
        dry_run=dry_run,
        tool_budget_exhausted=tool_budget_exhausted,
    )


def _extract_answer(state: dict[str, Any]) -> str:
    """Pull the final AIMessage content and sanitise it.

    Inputs entering the graph are already sanitised in `ingest_node`, and
    tool-returned `raw` fields are sanitised in `query_logs`, so a clean
    LLM cannot generate a secret it never saw. The sanitiser runs again
    here as defence-in-depth — matches the ADR-015 §8 promise that the
    response body never carries a credential.
    """
    messages = state.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = msg.content
            if isinstance(content, str):
                return sanitize_log_raw(content)
            # ChatOpenAI may return content as a list of blocks; flatten.
            if isinstance(content, list):
                return sanitize_log_raw("".join(str(b) for b in content))
            return sanitize_log_raw(str(content))
    return ""


def _extract_citations(state: dict[str, Any]) -> list[Citation]:
    """Re-shape the agent's CitedLogEntry list into the API Citation schema.

    Both schemas mirror a subset of `LogEntry`; the difference is `timestamp`
    is an ISO string in CitedLogEntry (tool-message-safe) and a `datetime`
    in Citation (Pydantic serialises it back to ISO in the response).
    """
    from datetime import datetime

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
                # Defence-in-depth — `query_logs` already sanitised this,
                # but running the sanitiser once more ensures any future
                # bypass cannot leak a credential into the response.
                raw=sanitize_log_raw(entry.raw),
                score=entry.score,
            )
        )
    return citations


def _is_openai_api_error(exc: BaseException) -> bool:
    try:
        from openai import APIError
    except ImportError:
        return False
    return isinstance(exc, APIError)


def _truncate(text: str) -> str:
    if len(text) <= _LOG_PREVIEW_LIMIT:
        return text
    return text[:_LOG_PREVIEW_LIMIT] + "…"
