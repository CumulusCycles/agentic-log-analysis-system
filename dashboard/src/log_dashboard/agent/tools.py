"""LangChain tools the agent can call: `query_logs` + `get_app_status`.

Both tools are constructed at graph-build time via factory functions that
close over `settings` + `vectorstore`. This avoids a global-state lookup
from inside the tool's body, which would make testing painful.

Returns `list[BaseTool]` so `model.bind_tools([...])` accepts the result
directly. The tool names and descriptions are what the LLM sees — keep
them tight and operator-flavoured ("logs from one of the four apps", not
"a vector store") since they drive routing decisions.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Annotated, Any

from langchain_core.tools import BaseTool, tool

from ..credentials import sanitize_log_raw
from ..ingest.reader import LogReaderError, read_recent_entries
from ..ingest.rollup import compute_app_status
from ..ingest.spec import APP_LOGS, APP_NAMES
from ..logging_setup import get_logger
from ..schemas import LogLevel
from .state import CitedLogEntry

if TYPE_CHECKING:
    from langchain_chroma import Chroma

    from ..config import Settings

log = get_logger("agent.tools")

# Hard caps the LLM cannot exceed regardless of what it asks for.
_QUERY_LOGS_TOP_K_MAX = 20
_QUERY_LOGS_TOP_K_DEFAULT = 10


def build_tools(settings: Settings, vectorstore: Chroma | None) -> list[BaseTool]:
    """Return the bound `[query_logs, get_app_status]` tools.

    `vectorstore` may be None when the dashboard is in degraded mode
    (Ollama unreachable at lifespan). In that case `query_logs` returns
    `{tool_error: "vectorstore_unavailable"}` so the LLM degrades gracefully
    without crashing the graph.
    """

    @tool
    def query_logs(
        query: Annotated[str, "Natural-language description of what to search for."],
        apps: Annotated[
            list[str] | None,
            "Optional filter — only return logs from these app names "
            "(shared-data-api, fnol, customer-portal, agent-portal).",
        ] = None,
        levels: Annotated[
            list[str] | None,
            "Optional filter — only return logs at these levels (DEBUG, INFO, WARN, ERROR).",
        ] = None,
        since_minutes: Annotated[
            int | None,
            "Optional filter — only return logs from the last N minutes.",
        ] = None,
        top_k: Annotated[
            int,
            "How many results to return (max 20, default 10).",
        ] = _QUERY_LOGS_TOP_K_DEFAULT,
    ) -> dict[str, Any]:
        """Semantic search over the dashboard's log corpus.

        Returns the most relevant log lines from across all four apps.
        Use this to find errors, warnings, or specific events the operator
        is asking about. Each result carries `app`, `level`, `timestamp`,
        `event`, `raw`, and a similarity `score` (lower = closer match).
        """
        if vectorstore is None:
            return {"results": [], "tool_error": "vectorstore_unavailable"}

        # Cap top_k regardless of what the LLM asked for.
        effective_k = max(1, min(int(top_k), _QUERY_LOGS_TOP_K_MAX))

        # Validate the apps filter — surface a clear error to the LLM so it
        # can self-correct rather than returning empty silently.
        if apps:
            unknown = [a for a in apps if a not in APP_NAMES]
            if unknown:
                return {"results": [], "tool_error": f"unknown_app(s): {','.join(unknown)}"}

        validated_levels = _validate_levels(levels)

        where = _build_where(apps, validated_levels, since_minutes)

        try:
            results = vectorstore.similarity_search_with_score(query, k=effective_k, filter=where)
        except Exception as exc:  # noqa: BLE001 — must not crash the graph
            log.warning("agent_query_logs_failed", error_class=type(exc).__name__)
            return {"results": [], "tool_error": "chroma_unreachable"}

        entries: list[dict[str, Any]] = []
        for doc, score in results:
            md = doc.metadata or {}
            try:
                level_val = str(md.get("level", "INFO"))
                # Skip docs whose level metadata is malformed.
                level = LogLevel(level_val)
            except ValueError:
                continue
            entries.append(
                CitedLogEntry(
                    id=str(md.get("id") or ""),
                    timestamp=str(md.get("timestamp_iso") or ""),
                    level=level,
                    app=str(md.get("app") or ""),
                    event=str(md.get("event") or ""),
                    # Defence-in-depth: sanitise BEFORE the LLM sees the raw line.
                    raw=sanitize_log_raw(str(md.get("raw") or "")),
                    score=float(score),
                ).model_dump()
            )
        return {"results": entries}

    @tool
    def get_app_status(
        app: Annotated[
            str | None,
            "Optional — one of shared-data-api, fnol, customer-portal, agent-portal. "
            "Omit to get all four.",
        ] = None,
    ) -> dict[str, Any]:
        """Return the current health status of one (or all) of the four apps.

        Each entry has `name`, `status` (ok / degraded / error), `file_present`,
        `last_seen_at`, and INFO / WARN / ERROR counts over the last 1h / 24h / 7d.

        Use this to answer "is X healthy?" without the operator having to
        switch tabs to the Overview page.
        """
        if app is not None and app not in APP_NAMES:
            return {"apps": [], "tool_error": f"unknown_app: {app}"}

        now = datetime.now(tz=UTC)
        targets = [a for a in APP_LOGS if app is None or a.name == app]
        out: list[dict[str, Any]] = []
        for app_log in targets:
            try:
                entries = read_recent_entries(
                    app_log,
                    volume_root=settings.log_volume_root,
                    limit=settings.logs_tail_default,
                )
            except LogReaderError:
                out.append(
                    {
                        "name": app_log.name,
                        "status": "error",
                        "file_present": False,
                        "last_seen_at": None,
                    }
                )
                continue
            status = compute_app_status(app_log.name, entries, now=now, file_present=True)
            out.append(status.model_dump(mode="json"))
        return {"apps": out}

    return [query_logs, get_app_status]


def _validate_levels(levels: list[str] | None) -> list[LogLevel] | None:
    if not levels:
        return None
    out: list[LogLevel] = []
    for lvl in levels:
        try:
            out.append(LogLevel(lvl.upper()))
        except ValueError:
            continue
    return out or None


def _build_where(
    apps: list[str] | None,
    levels: list[LogLevel] | None,
    since_minutes: int | None,
) -> dict[str, Any] | None:
    """Translate filters into a Chroma `$where` clause. Mirrors the shape
    used by `routers/search.py` so the two query paths stay consistent."""
    clauses: list[dict[str, Any]] = []
    if apps:
        clauses.append({"app": {"$in": apps}})
    if levels:
        clauses.append({"level": {"$in": [lvl.value for lvl in levels]}})
    if since_minutes is not None and since_minutes > 0:
        cutoff = datetime.now(tz=UTC) - timedelta(minutes=since_minutes)
        clauses.append({"timestamp_epoch": {"$gte": cutoff.timestamp()}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


# Async wrappers — exposed for the chat route to call the sync similarity
# search off the event loop without copying the validation logic. Kept here
# rather than in `graph.py` so the tools module owns its async boundary.


async def query_logs_async(
    settings: Settings,
    vectorstore: Chroma | None,
    *,
    query: str,
    apps: list[str] | None = None,
    levels: list[str] | None = None,
    since_minutes: int | None = None,
    top_k: int = _QUERY_LOGS_TOP_K_DEFAULT,
) -> dict[str, Any]:
    """Sync `query_logs` body re-exposed off the event loop. Convenience for
    tests + future direct callers; the LangGraph path goes through `ToolNode`."""
    tools = build_tools(settings, vectorstore)
    query_logs_tool = next(t for t in tools if t.name == "query_logs")
    return await asyncio.to_thread(
        query_logs_tool.invoke,
        {
            "query": query,
            "apps": apps,
            "levels": levels,
            "since_minutes": since_minutes,
            "top_k": top_k,
        },
    )
