"""Proactive background scan loop — wakes every N seconds, asks the same
LangGraph agent that backs `/api/chat` to scan the recent log corpus, and
appends anomalies to an in-process ring buffer surfaced via `/api/status`.

Safety asymmetry (mirrors PR 4a's `DASHBOARD_LLM_DRY_RUN`): real scans only
fire when BOTH

  * `settings.proactive_scan_enabled` is True (default: False)
  * `settings.dashboard_llm_dry_run` is False (default: True)

Either alone is safe. Dry-run wakes the loop on schedule, logs
`proactive_scan_skipped reason=llm_dry_run`, and goes back to sleep —
zero cost. ADR-016 documents the design.

The scan re-uses the compiled graph attached to `app.state.agent_graph`
during lifespan, so every cost cap, credential redaction layer, and
LangSmith metadata tag from PR 4a applies transparently here.

Findings are restart-lossy by design — same posture as the Agitator's
`RunRegistry`.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage

from ..logging_setup import get_logger
from ..schemas import ProactiveFinding, ProactiveSeverity
from .proactive_prompt import NO_ANOMALIES_SENTINEL, render_prompt
from .responses import extract_answer, extract_citations, is_openai_api_error
from .sessions import new_session_id, thread_id_for

if TYPE_CHECKING:
    from fastapi import FastAPI
    from langchain_chroma import Chroma
    from langgraph.graph.state import CompiledStateGraph

    from ..config import Settings
    from ..schemas import Citation
    from .sessions import SessionIndex

log = get_logger("agent.proactive")

# `jwt_sub` value for proactive-scan threads. Distinct from any real admin
# UUID so the SessionIndex LRU groups all scan threads under one identifier
# and so LangSmith metadata is filterable.
PROACTIVE_JWT_SUB = "system:proactive-scan"


class FindingsBuffer:
    """Ring buffer of proactive-scan findings + scan-loop metadata.

    Bounded by `maxlen` (default 50) so the deque can't grow without limit.
    `last_scan_at` / `next_scan_at` are written by the loop after every
    iteration so the operator-facing `/api/status` can report scheduling
    state alongside the findings.
    """

    def __init__(self, maxlen: int = 50) -> None:
        self._findings: deque[ProactiveFinding] = deque(maxlen=maxlen)
        self.last_scan_at: datetime | None = None
        self.next_scan_at: datetime | None = None

    def append(self, finding: ProactiveFinding) -> None:
        self._findings.append(finding)

    def recent(self, limit: int) -> list[ProactiveFinding]:
        """Return the `limit` most recent findings, newest first."""
        if limit <= 0:
            return []
        # Reverse-iterate the deque so we never copy the whole thing when
        # `limit` << len(self._findings).
        out: list[ProactiveFinding] = []
        for finding in reversed(self._findings):
            out.append(finding)
            if len(out) >= limit:
                break
        return out

    def __len__(self) -> int:
        return len(self._findings)


def _severity_for(citations: list[Citation]) -> ProactiveSeverity:
    """Derive a finding's severity from its citation set.

    Deterministic — no LLM, no surprise. Any ERROR in the citations wins;
    else any WARN; else info. The agent can describe the anomaly however
    it wants, but the UI's pill color is grounded in the underlying log
    levels the citations point at.
    """
    has_error = False
    has_warn = False
    for cite in citations:
        # LogLevel is a str-Enum; compare by `.value`.
        if cite.level.value == "ERROR":
            has_error = True
        elif cite.level.value == "WARN":
            has_warn = True
    if has_error:
        return "error"
    if has_warn:
        return "warn"
    return "info"


def _new_finding_id() -> str:
    """`proactive:{uuid4-hex}` — opaque to the client; React list key only.

    Distinct shape from `LogEntry.id` (which is `{app}:{16 hex}`) so the
    `/errors/{id}` regex naturally rejects a finding id.
    """
    return f"proactive:{uuid.uuid4().hex}"


async def _run_one_scan(
    *,
    graph: CompiledStateGraph,
    vectorstore: Chroma | None,
    settings: Settings,
    session_index: SessionIndex,
) -> ProactiveFinding | None:
    """One scan iteration. Returns the resulting finding, or None when the
    agent declared the scan quiet (`NO_ANOMALIES`) or when degraded mode
    short-circuits the invocation.

    Importable in tests — the loop is a sleep + this call.
    """
    if vectorstore is None:
        # Degraded mode (no OpenAI key → no Chroma). The agent could still
        # be invoked but `query_logs` would return tool_error and the
        # answer would be useless. Skip to keep `last_scan_at` honest.
        log.info("proactive_scan_skipped", reason="vectorstore_unavailable")
        return None

    session_id = new_session_id()
    thread_id = thread_id_for(PROACTIVE_JWT_SUB, session_id)
    await session_index.touch(thread_id)

    started_at = datetime.now(tz=UTC)
    prompt = render_prompt(settings.proactive_scan_lookback_minutes)

    config = {
        "configurable": {"thread_id": thread_id},
        "metadata": {
            "session_id": session_id,
            "jwt_sub": PROACTIVE_JWT_SUB,
            "dry_run": settings.dashboard_llm_dry_run,
            "proactive_scan": True,
            "lookback_minutes": settings.proactive_scan_lookback_minutes,
        },
    }

    initial_state: dict = {
        "messages": [HumanMessage(content=prompt)],
        "session_id": session_id,
        "jwt_sub": PROACTIVE_JWT_SUB,
        "citations": [],
        "dry_run": settings.dashboard_llm_dry_run,
        "tool_budget_remaining": settings.llm_max_tool_calls_per_request,
        "tool_budget_exhausted": False,
    }

    log.info(
        "proactive_scan_started",
        session_id=session_id,
        lookback_minutes=settings.proactive_scan_lookback_minutes,
        dry_run=settings.dashboard_llm_dry_run,
    )

    try:
        result = await graph.ainvoke(initial_state, config=config)
    except Exception as exc:  # noqa: BLE001 — loop must survive bad iterations
        if is_openai_api_error(exc):
            log.warning(
                "proactive_scan_upstream_failure",
                session_id=session_id,
                error_class=type(exc).__name__,
            )
            return None
        log.warning(
            "proactive_scan_error",
            session_id=session_id,
            error_class=type(exc).__name__,
        )
        return None

    answer = extract_answer(result)
    completed_at = datetime.now(tz=UTC)

    # Sentinel short-circuit — leading whitespace tolerated, exact-string
    # match for the sentinel token itself. The agent is instructed to emit
    # `NO_ANOMALIES` and nothing else, but a stray trailing newline is fine.
    if answer.strip().startswith(NO_ANOMALIES_SENTINEL):
        log.info(
            "proactive_scan_complete",
            session_id=session_id,
            outcome="no_anomalies",
            dry_run=bool(result.get("dry_run", settings.dashboard_llm_dry_run)),
        )
        return None

    citations = extract_citations(result)
    finding = ProactiveFinding(
        id=_new_finding_id(),
        scan_started_at=started_at,
        scan_completed_at=completed_at,
        summary=answer,
        severity=_severity_for(citations),
        citations=citations,
        dry_run=bool(result.get("dry_run", settings.dashboard_llm_dry_run)),
    )
    log.info(
        "proactive_scan_complete",
        session_id=session_id,
        outcome="finding",
        severity=finding.severity,
        citation_count=len(citations),
        dry_run=finding.dry_run,
    )
    return finding


async def run_proactive_scan_loop(app: FastAPI, settings: Settings) -> None:
    """Background loop. Sleeps for the configured interval, runs one scan,
    appends any resulting finding to `app.state.findings_buffer`.

    Cancellation: the lifespan calls `task.cancel()` on shutdown. The loop
    re-raises `CancelledError` so the task transitions to cancelled cleanly.
    """
    buffer: FindingsBuffer = app.state.findings_buffer
    interval = settings.proactive_scan_interval_seconds
    # Stamp `next_scan_at` immediately so the first /api/status response
    # has a meaningful value even before the first scan fires.
    buffer.next_scan_at = datetime.now(tz=UTC) + timedelta(seconds=interval)

    while True:
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise

        if settings.dashboard_llm_dry_run:
            # Opt-in chain: real scans need DRY_RUN=false AND ENABLED=true.
            # Log + continue so the loop scheduling stays visible without
            # touching OpenAI.
            log.info("proactive_scan_skipped", reason="llm_dry_run")
            buffer.last_scan_at = datetime.now(tz=UTC)
            buffer.next_scan_at = buffer.last_scan_at + timedelta(seconds=interval)
            continue

        graph = getattr(app.state, "agent_graph", None)
        vectorstore = getattr(app.state, "vectorstore", None)
        session_index = getattr(app.state, "session_index", None)
        if graph is None or session_index is None:
            log.warning(
                "proactive_scan_skipped",
                reason="agent_state_unavailable",
                has_graph=graph is not None,
                has_session_index=session_index is not None,
            )
            buffer.last_scan_at = datetime.now(tz=UTC)
            buffer.next_scan_at = buffer.last_scan_at + timedelta(seconds=interval)
            continue

        try:
            finding = await _run_one_scan(
                graph=graph,
                vectorstore=vectorstore,
                settings=settings,
                session_index=session_index,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — loop must survive bad iterations
            log.warning(
                "proactive_scan_iteration_failed",
                error_class=type(exc).__name__,
            )
            finding = None

        if finding is not None:
            buffer.append(finding)

        buffer.last_scan_at = datetime.now(tz=UTC)
        buffer.next_scan_at = buffer.last_scan_at + timedelta(seconds=interval)
