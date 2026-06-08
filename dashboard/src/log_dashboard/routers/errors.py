"""GET /api/errors/{entry_id} — Error Detail + Suggested Fix.

Flow per request:
1. Validate `entry_id` shape (`{app}:{16 hex}` — same as Chroma doc ID)
2. Look the entry up via Chroma `_collection.get(ids=[...])` — single O(1)
   call, no embedding round-trip needed since we already know the key
3. 404 if missing (entry never passed the ingest gate, or Ollama was
   unreachable when the line was emitted)
4. Synthesise a HumanMessage that frames the entry for the agent
5. Token-cap check (reused from `/api/chat`)
6. Mint a fresh `session_id`, register with `SessionIndex`
7. Invoke the agent graph — same compiled graph used by `/api/chat`
8. Build `ErrorDetailResponse{entry, analysis}` from the final state

Only WARN/ERROR entries are eligible — route-level gate. Post-Phase-8
(ADR-017) Chroma admits all levels for baseline awareness, so this check
is what keeps Error Detail focused on actionable signal.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from langchain_core.messages import HumanMessage

from ..agent.responses import (
    count_tokens,
    extract_answer,
    extract_citations,
    is_llm_api_error,
)
from ..agent.sessions import new_session_id, thread_id_for
from ..auth.jwt import get_current_admin
from ..config import Settings, get_settings
from ..credentials import sanitize_log_raw
from ..ingest.spec import APP_NAMES
from ..ingest.vectorstore import lookup_entry_by_id
from ..logging_setup import get_logger
from ..schemas import AgentAnalysis, ErrorDetailResponse, LogLevel

if TYPE_CHECKING:
    from langchain_chroma import Chroma
    from langgraph.graph.state import CompiledStateGraph

    from ..agent.sessions import SessionIndex

router = APIRouter(tags=["errors"])
log = get_logger("errors")

# Mirrors `make_doc_id`'s output format. App segment is restricted to the
# closed `APP_NAMES` vocabulary so a typo like `Fnol:abc...` is rejected at
# the validation boundary without burning a Chroma round-trip.
_ENTRY_ID_RE = re.compile(rf"^(?:{'|'.join(re.escape(a) for a in APP_NAMES)}):[0-9a-f]{{16}}$")

# The prompt the agent receives. Mirrors what an operator would type into
# the chat surface. Kept short — the agent's `query_logs` tool does the
# heavy lifting of finding correlated entries; this prompt just frames the
# subject. The trailing `Use query_logs ...` line is a soft nudge, not a
# command — the analyse node decides whether tool use is warranted.
_ANALYSE_TEMPLATE = (
    "Analyse this error and suggest a fix.\n\n"
    "App: {app}\n"
    "Level: {level}\n"
    "Event: {event}\n"
    "Timestamp: {timestamp}\n\n"
    "Raw log line:\n{raw}\n\n"
    "Use the `query_logs` tool to find related entries that might explain "
    "the root cause, then provide a concise suggested remediation."
)


def _get_vectorstore(request: Request) -> Chroma | None:
    return getattr(request.app.state, "vectorstore", None)


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


@router.get("/errors/{entry_id}", response_model=ErrorDetailResponse)
async def get_error_detail(
    entry_id: str,
    request: Request,
    payload: dict[str, Any] = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> ErrorDetailResponse:
    if not _ENTRY_ID_RE.match(entry_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="malformed entry id — expected `{app}:{16 hex chars}`",
        )

    store = _get_vectorstore(request)
    if store is None:
        # Ollama unreachable → no Chroma → no Error Detail. The
        # operator-facing /api/logs view keeps working in this mode; only
        # the agent-backed surfaces degrade.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="error detail is unavailable — OLLAMA_BASE_URL is unreachable",
        )

    entry = lookup_entry_by_id(store, entry_id)
    if entry is None:
        # Either the ID isn't in Chroma (parser rejected it, or it was
        # ingested while Ollama was down) or Chroma returned malformed
        # metadata (already logged in `lookup_entry_by_id`). 404 in both
        # cases — the operator can't do anything different.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="entry not found",
        )

    # Route-level gate: only WARN/ERROR are eligible for analysis. Post-
    # Phase-8 (ADR-017) Chroma admits all levels for RAG baseline; this
    # branch keeps Error Detail scoped to actionable entries.
    if entry.level not in (LogLevel.WARN, LogLevel.ERROR):
        log.info(
            "error_detail_rejected_non_error_level",
            entry_id=entry_id,
            level=entry.level.value,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="entry not eligible for analysis (level must be WARN or ERROR)",
        )

    # Sanitise the raw line on TWO paths — the LLM context and the response
    # body. The 7d ingest pipeline only stores already-app-sanitised log
    # lines, but the rule in `feedback_never_log_credentials` is paranoid by
    # design: never let an unredacted credential cross into the LLM /
    # LangSmith trace OR the response body. The same value is sanitised on
    # the citation path in `extract_citations`, so the whole response is
    # credential-free even if an upstream-app bug put a secret in a log line.
    safe_raw = sanitize_log_raw(entry.raw)
    # Pydantic v2 immutable update — never mutate the source LogEntry in
    # place. If `lookup_entry_by_id` ever returned a shared / cached object
    # (it doesn't today, but Chroma client behaviours change), an in-place
    # write would leak the unsanitised string back through that cache.
    entry = entry.model_copy(update={"raw": safe_raw})
    synthesised_message = _ANALYSE_TEMPLATE.format(
        app=entry.app,
        level=entry.level.value,
        event=entry.event,
        timestamp=entry.timestamp.isoformat(),
        raw=safe_raw,
    )

    token_count = count_tokens(synthesised_message)
    if token_count > settings.llm_max_input_tokens_per_request:
        # An extremely verbose raw line (huge stack trace) could blow the cap.
        # Surface 413 so the operator knows the analysis didn't silently
        # truncate. The /api/logs view is unaffected — the full raw line is
        # still browseable there.
        log.info(
            "error_detail_rejected_token_cap",
            entry_id=entry_id,
            tokens=token_count,
            cap=settings.llm_max_input_tokens_per_request,
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"error context exceeds input token cap "
                f"({token_count} > {settings.llm_max_input_tokens_per_request})"
            ),
        )

    jwt_sub = str(payload.get("sub") or "admin")
    session_id = new_session_id()
    thread_id = thread_id_for(jwt_sub, session_id)
    await _get_session_index(request).touch(thread_id)

    graph = _get_graph(request)
    config = {
        "configurable": {"thread_id": thread_id},
        "metadata": {
            "session_id": session_id,
            "jwt_sub": jwt_sub,
            "dry_run": settings.dashboard_llm_dry_run,
            "error_detail_id": entry_id,
        },
    }

    log.info(
        "error_detail_started",
        entry_id=entry_id,
        session_id=session_id,
        dry_run=settings.dashboard_llm_dry_run,
        tokens=token_count,
    )

    initial_state: dict[str, Any] = {
        "messages": [HumanMessage(content=synthesised_message)],
        "session_id": session_id,
        "jwt_sub": jwt_sub,
        "citations": [],
        "dry_run": settings.dashboard_llm_dry_run,
        "tool_budget_remaining": settings.llm_max_tool_calls_per_request,
        "tool_budget_exhausted": False,
    }

    try:
        result = await graph.ainvoke(initial_state, config=config)
    except Exception as exc:
        if is_llm_api_error(exc):
            log.warning(
                "error_detail_upstream_failure",
                entry_id=entry_id,
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
        "error_detail_complete",
        entry_id=entry_id,
        session_id=session_id,
        dry_run=dry_run,
        citation_count=len(citations),
        tool_budget_exhausted=tool_budget_exhausted,
    )

    return ErrorDetailResponse(
        entry=entry,
        analysis=AgentAnalysis(
            answer=answer,
            citations=citations,
            dry_run=dry_run,
            tool_budget_exhausted=tool_budget_exhausted,
        ),
    )
