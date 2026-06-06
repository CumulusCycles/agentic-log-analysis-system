import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .agent.graph import build_agent_graph
from .agent.proactive import FindingsBuffer, run_proactive_scan_loop
from .agent.sessions import SessionIndex
from .agitator.runs import RunRegistry
from .auth.password import hash_password
from .config import get_settings
from .exception_handlers import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from .ingest.backfill import run_initial_backfill
from .ingest.vectorstore import (
    build_vectorstore,
    configure_langsmith,
    is_embeddings_disabled,
)
from .ingest.watcher import LogVolumeWatcher
from .logging_setup import configure_logging, get_logger
from .routers import agitator, auth, chat, chroma_stats, errors, health, logs, search, status

# Paths FastAPI auto-mounts that the SPA catch-all MUST NOT intercept.
# Swagger UI is intentionally exposed per ADR-001 — the dashboard's audience
# is a single admin/operator, and Swagger is a strict diagnostic win
# (especially once 7e lands /api/chat).
_FASTAPI_RESERVED_PREFIXES = ("docs", "redoc", "openapi.json")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(log_file_path=None)
    log = get_logger(__name__)

    async def _backfill_and_start_watcher(app: FastAPI) -> None:
        """Run initial backfill in a thread, then start the watcher with the
        offsets it returns. Scheduled as a background asyncio task so the
        lifespan can yield immediately (cold-start backfill takes ~2 min on
        ~20K log lines and would otherwise hold the healthcheck off too long).
        """
        try:
            store = app.state.vectorstore
            log.info("backfill_started")
            backfill_results = await asyncio.to_thread(run_initial_backfill, settings, store)
            log.info(
                "backfill_complete",
                totals={r.app: r.embedded for r in backfill_results},
            )
            initial_offsets = {r.app: r.active_size_bytes for r in backfill_results}
            if settings.watcher_enabled:
                watcher = LogVolumeWatcher(settings, store, initial_offsets=initial_offsets)
                watcher.start()
                app.state.watcher = watcher
            app.state.backfill_complete = True
        except Exception as exc:  # noqa: BLE001 — must surface but never crash startup
            log.warning(
                "backfill_failed",
                error_class=type(exc).__name__,
            )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Bcrypt-hash the admin password once at startup and drop the
        # plaintext reference. The hash lives on app.state for the lifetime
        # of the process; the plaintext is never persisted or logged.
        app.state.admin_password_hash = hash_password(settings.admin_password)

        # Phase 7d: Chroma + embeddings + watcher. Degrades cleanly when the
        # OpenAI key is missing — /api/logs and /api/status keep working,
        # /api/logs/search returns 503.
        app.state.vectorstore = None
        app.state.watcher = None
        app.state.backfill_complete = False
        # PR 3: bundled Agitator load driver — in-memory ring buffer of runs.
        # No persistence by design; restart clears history.
        app.state.agitator_runs = RunRegistry()
        backfill_task: asyncio.Task[None] | None = None

        if is_embeddings_disabled(settings):
            log.info(
                "embeddings_disabled",
                reason="missing_or_placeholder_openai_key",
            )
            app.state.backfill_complete = True
        else:
            configure_langsmith(settings)
            # Build the vectorstore immediately so the search endpoint becomes
            # queryable as soon as lifespan yields. The collection may be
            # empty (or partial) until backfill completes; results land
            # incrementally as the background task fills it in.
            app.state.vectorstore = build_vectorstore(settings)
            backfill_task = asyncio.create_task(_backfill_and_start_watcher(app))

        # Phase 7e (PR 4a): LangGraph agent + /api/chat. The graph and its
        # InMemorySaver checkpointer + SessionIndex are built unconditionally
        # — `vectorstore=None` is permitted so the chat route still responds
        # in degraded mode (the `query_logs` tool returns a tool_error).
        from langgraph.checkpoint.memory import InMemorySaver

        agent_checkpointer = InMemorySaver()
        app.state.session_index = SessionIndex(
            checkpointer=agent_checkpointer, max_entries=settings.session_index_max
        )
        app.state.agent_graph = build_agent_graph(
            settings, app.state.vectorstore, agent_checkpointer
        )

        # Phase 7e (PR 4c): proactive background scan. The findings buffer
        # is created unconditionally so `/api/status` can always report
        # `proactive_findings: []` + `scan_enabled` without state checks.
        # The loop task only starts when the operator opts in via
        # `DASHBOARD_PROACTIVE_SCAN_ENABLED=true` — dry-run is a soft gate
        # the loop applies per-iteration so the scheduling stays visible
        # even when DRY_RUN=true.
        app.state.findings_buffer = FindingsBuffer()
        proactive_task: asyncio.Task[None] | None = None
        if settings.proactive_scan_enabled:
            proactive_task = asyncio.create_task(run_proactive_scan_loop(app, settings))
            log.info(
                "proactive_scan_loop_started",
                interval_seconds=settings.proactive_scan_interval_seconds,
                lookback_minutes=settings.proactive_scan_lookback_minutes,
                dry_run=settings.dashboard_llm_dry_run,
            )

        log.info("startup_complete")
        yield

        if backfill_task is not None and not backfill_task.done():
            backfill_task.cancel()
        if proactive_task is not None and not proactive_task.done():
            proactive_task.cancel()
            # Drain the task so an in-flight `graph.ainvoke` (or any LangSmith
            # trace it owns) finalises before we tear down dependent state
            # (vectorstore, session_index). Without the await, cancel() only
            # signals — the task can keep running past lifespan exit.
            try:
                await proactive_task
            except asyncio.CancelledError:
                pass
        if app.state.watcher is not None:
            app.state.watcher.stop()
        # Drain any in-flight Agitator runs so shutdown is clean.
        await app.state.agitator_runs.cancel_all()
        # Drop every tracked LangGraph thread so the in-process checkpointer
        # is empty on next start.
        await app.state.session_index.aclose()

    app = FastAPI(
        title="Agentic Log Analysis Dashboard",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health.router)
    app.include_router(auth.router, prefix="/api/auth")
    app.include_router(logs.router, prefix="/api")
    app.include_router(status.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(agitator.router, prefix="/api/agitator")
    app.include_router(chat.router, prefix="/api")
    app.include_router(errors.router, prefix="/api")
    app.include_router(chroma_stats.router, prefix="/api")

    # Static React build — mounted under /assets/ for hashed bundles, with a
    # catch-all GET that serves index.html for every other unknown path so the
    # client-side React Router can take over. The catch-all explicitly skips
    # FastAPI's own /docs, /redoc, /openapi.json so Swagger continues to work.
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        dist_resolved = dist.resolve()
        index_html = dist_resolved / "index.html"
        app.mount("/assets", StaticFiles(directory=str(dist_resolved / "assets")), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            # Never shadow FastAPI's Swagger / ReDoc / OpenAPI auto-mounts.
            if full_path.startswith(_FASTAPI_RESERVED_PREFIXES):
                raise HTTPException(status_code=404, detail="Not Found")
            # Serve static files from dist root if they exist (favicon, etc.),
            # otherwise fall through to index.html for SPA routes. Resolve
            # candidate then verify it stays under dist_resolved to block
            # path-traversal like `../../etc/passwd`.
            if full_path:
                candidate = (dist_resolved / full_path).resolve()
                if candidate.is_file() and candidate.is_relative_to(dist_resolved):
                    return FileResponse(candidate)
            if index_html.is_file():
                return FileResponse(index_html)
            raise HTTPException(status_code=404, detail="Not Found")

    else:
        log.warning("frontend_dist_missing", expected=str(dist))

    return app


app = create_app()
