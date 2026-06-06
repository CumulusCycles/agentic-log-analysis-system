"""POST /api/chat — LangGraph agent invocation.

Two response shapes share the same agent invocation:

- Non-streaming (`streaming=false`, default) — `await graph.ainvoke(...)`,
  returns JSON `ChatResponse` once the final node runs.
- Streaming (`streaming=true`, PR 4b) — `graph.astream(stream_mode="updates")`
  yields one SSE `event: node` per node completion plus a single
  `event: complete` with the same fields the JSON path would have returned.
  Frontend renders per-node status (`thinking… → searching logs… → …`)
  while the agent runs, then swaps in the final answer.

Shared pre-flight (auth, sanitisation, token cap, session minting) runs
before either path branches — early rejections always return JSON so the
client doesn't need an SSE parser to read `401 / 413 / 503`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from ..agent.responses import (
    count_tokens,
    extract_answer,
    extract_citations,
    is_openai_api_error,
)
from ..agent.sessions import new_session_id, thread_id_for
from ..auth.jwt import get_current_admin
from ..config import Settings, get_settings
from ..credentials import sanitize_user_input
from ..logging_setup import get_logger
from ..schemas import ChatRequest, ChatResponse

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from ..agent.sessions import SessionIndex

router = APIRouter(tags=["chat"])
log = get_logger("chat")

# Truncate user message previews in log lines so a paragraph-long question
# doesn't balloon the log file. The query itself is admin input, not a
# credential, but bounded log lines are easier to consume downstream.
_LOG_PREVIEW_LIMIT = 200

# Counters surfaced to the client per node. Keeping the per-node payload
# small means the SSE stream stays under a kilobyte for the whole 5-node
# loop — the full state would balloon as the LLM messages accumulate.
_NODE_STATUS_FIELDS = ("tool_budget_remaining", "tool_budget_exhausted")


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


@router.post(
    "/chat",
    # The endpoint returns either a JSON `ChatResponse` (default) or an
    # SSE `text/event-stream` (when `streaming=true`). `response_model=None`
    # tells FastAPI not to infer a single Pydantic response schema; the
    # `responses` dict documents both content types in the OpenAPI surface
    # so Swagger users can see the polymorphism.
    response_model=None,
    responses={
        200: {
            "content": {
                "application/json": {},
                "text/event-stream": {},
            },
        },
    },
)
async def post_chat(
    body: ChatRequest,
    request: Request,
    payload: dict[str, Any] = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> Response:
    # Sanitise the message BEFORE token counting + logging. Defence-in-depth:
    # `ingest_node` runs the same sanitiser, but this router never sees the
    # raw secret in its preview log line.
    message_sanitised = sanitize_user_input(body.message)

    # Cost guard. Counted against the chat model's encoding so we reject
    # before the LangGraph dispatcher spends anything. Applies to both
    # streaming and non-streaming paths.
    token_count = count_tokens(message_sanitised, settings.openai_chat_model)
    if token_count > settings.llm_max_input_tokens_per_request:
        log.info(
            "chat_rejected_token_cap",
            tokens=token_count,
            cap=settings.llm_max_input_tokens_per_request,
            streaming=body.streaming,
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
            "streaming": body.streaming,
        },
    }

    log.info(
        "chat_started",
        session_id=session_id,
        dry_run=settings.dashboard_llm_dry_run,
        streaming=body.streaming,
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

    if body.streaming:
        return StreamingResponse(
            _stream_chat_events(
                graph=graph,
                initial_state=initial_state,
                config=config,
                session_id=session_id,
                default_dry_run=settings.dashboard_llm_dry_run,
                request=request,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                # Defensive: ensures any forward proxy between FastAPI and the
                # browser (none in this stack today; one day there will be)
                # doesn't buffer the chunks before flushing.
                "X-Accel-Buffering": "no",
            },
        )

    try:
        result = await graph.ainvoke(initial_state, config=config)
    except Exception as exc:
        # Surface OpenAI / upstream LLM failures as 502; everything else
        # (programming errors, schema issues) bubbles to the global 500
        # handler. `is_openai_api_error` imports `openai` lazily so dry-run
        # installs don't pay the import cost.
        if is_openai_api_error(exc):
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

    answer = extract_answer(result)
    citations = extract_citations(result)
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


async def _stream_chat_events(
    *,
    graph: CompiledStateGraph,
    initial_state: dict[str, Any],
    config: dict[str, Any],
    session_id: str,
    default_dry_run: bool,
    request: Request,
) -> AsyncIterator[bytes]:
    """SSE generator — one `event: node` per node, one `event: complete` at end.

    Per-node payload is a status snapshot (not the full state) so the wire
    cost stays bounded; the final answer + citations land in `event: complete`
    via the same `ChatResponse` shape the non-streaming path emits, so the
    two surfaces cannot drift.

    Client-disconnect handling: between node emissions we check
    `request.is_disconnected()` and break out before the next graph step
    runs. The existing tool-call cap already bounds spend, but a client
    that disconnects mid-stream shouldn't keep burning OpenAI tokens just
    to populate a checkpoint nobody will read.

    Upstream LLM failures during the stream emit a single `event: error`
    then close cleanly — the frontend's onError handler tears down the
    fetch-reader.
    """
    aborted = False
    try:
        async for chunk in graph.astream(initial_state, config=config, stream_mode="updates"):
            # `stream_mode="updates"` yields {node_name: partial_state_update}.
            # In this graph each step only ever updates one node at a time,
            # but we iterate the dict to stay correct if that ever changes.
            for node_name, partial in chunk.items():
                payload: dict[str, Any] = {"node": node_name}
                for field in _NODE_STATUS_FIELDS:
                    if field in partial:
                        payload[field] = partial[field]
                # `correlate` adds citations; surface a running count so the
                # UI can show "found 3 related entries" mid-stream.
                if "citations" in partial:
                    payload["citation_count"] = len(partial["citations"] or [])
                yield _sse_event("node", payload)
            if await request.is_disconnected():
                # Stop iterating the graph — no point producing tokens for a
                # gone client. We do NOT emit `event: error` because the
                # client is gone; just exit the generator.
                aborted = True
                log.info(
                    "chat_stream_aborted_client_disconnected",
                    session_id=session_id,
                )
                return
    except Exception as exc:
        if is_openai_api_error(exc):
            log.warning(
                "chat_upstream_failure",
                session_id=session_id,
                error_class=type(exc).__name__,
                streaming=True,
            )
            yield _sse_event(
                "error",
                {"detail": "upstream LLM unavailable — try again shortly"},
            )
            return
        # Programming / schema errors — still emit a structured close so the
        # client doesn't see a half-closed connection without explanation.
        log.warning(
            "chat_stream_failed",
            session_id=session_id,
            error_class=type(exc).__name__,
        )
        yield _sse_event("error", {"detail": "stream failed unexpectedly"})
        return

    if aborted:
        return

    # The accumulated state lives in the checkpointer; fetch it once after
    # the stream completes so we can re-use the same response shape the
    # non-streaming path emits. `snapshot.values` may be empty or missing if
    # the graph errored before any checkpoint was written.
    snapshot = await graph.aget_state(config)
    final: dict[str, Any] = snapshot.values if snapshot is not None and snapshot.values else {}
    answer = extract_answer(final)
    citations = extract_citations(final)
    dry_run = bool(final.get("dry_run", default_dry_run))
    tool_budget_exhausted = bool(final.get("tool_budget_exhausted", False))

    log.info(
        "chat_complete",
        session_id=session_id,
        dry_run=dry_run,
        citation_count=len(citations),
        tool_budget_exhausted=tool_budget_exhausted,
        streaming=True,
    )

    # Re-use ChatResponse's serializer so the SSE `complete` event mirrors
    # the JSON `POST /api/chat` body exactly. Adding a non-JSON-native field
    # to Citation/ChatResponse in the future cannot cause the two surfaces
    # to drift — they go through the same Pydantic encoder.
    complete = ChatResponse(
        answer=answer,
        citations=citations,
        session_id=session_id,
        dry_run=dry_run,
        tool_budget_exhausted=tool_budget_exhausted,
    )
    yield _sse_event("complete", complete.model_dump(mode="json"))


def _sse_event(event: str, data: dict[str, Any]) -> bytes:
    """Format one SSE event. Keep the encoding here, not at call sites."""
    # `default=str` covers datetime + any stray non-JSON-native types (e.g.
    # if a future node adds a UUID to the state dict).
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()


def _truncate(text: str) -> str:
    if len(text) <= _LOG_PREVIEW_LIMIT:
        return text
    return text[:_LOG_PREVIEW_LIMIT] + "…"
