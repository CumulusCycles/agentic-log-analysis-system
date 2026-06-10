from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from .schemas import LogLevel


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        populate_by_name=True,
    )

    # Standalone JWT — independent of the Shared Data API. The dashboard signs
    # its own admin tokens so it stays usable when SDA is down (ADR-006).
    jwt_secret: str = Field(alias="DASHBOARD_JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="DASHBOARD_JWT_ALGORITHM")
    jwt_expires_minutes: int = Field(default=60, alias="DASHBOARD_JWT_EXPIRES_MINUTES")

    # Single admin, supplied entirely by env. The plaintext password is read
    # once at startup, bcrypt-hashed, and the plaintext reference is dropped
    # from app state.
    admin_username: str = Field(alias="DASHBOARD_ADMIN_USERNAME")
    admin_password: str = Field(alias="DASHBOARD_ADMIN_PASSWORD")

    # --- Phase 7d: Chroma + embeddings + semantic search ---

    chroma_url: str = Field(
        default="http://chroma:8000",
        alias="DASHBOARD_CHROMA_URL",
    )
    chroma_collection: str = Field(
        default="dashboard-logs",
        alias="DASHBOARD_CHROMA_COLLECTION",
    )

    # Wall-clock cap on Chroma HTTP calls (forwarded into chromadb's
    # `chroma_query_request_timeout_seconds` + `chroma_sysdb_request_timeout_seconds`).
    # Symmetric with `llm_timeout_seconds` — v1.1.1 closed the Ollama half of
    # the asymmetric-hang risk; v1.1.2 closes the Chroma half. A hung Chroma
    # would otherwise stall every code path that reads or writes the
    # vectorstore (chat, search, error-detail, proactive scan, backfill, watcher).
    chroma_timeout_seconds: int = Field(
        default=60, alias="DASHBOARD_CHROMA_TIMEOUT_SECONDS", ge=5, le=600
    )

    # Phase 8 / ADR-017 — local AI via Ollama. The dashboard MUST stay
    # usable for /api/logs and /api/status when Ollama is unreachable
    # (ADR-006 spirit); `is_embeddings_disabled` in vectorstore.py probes
    # the base URL at lifespan and degrades search to 503 if it's down.
    ollama_base_url: str = Field(
        default="http://ollama:11434",
        alias="OLLAMA_BASE_URL",
    )
    dashboard_llm_model: str = Field(
        default="llama3.1:8b",
        alias="DASHBOARD_LLM_MODEL",
    )
    dashboard_embed_model: str = Field(
        default="nomic-embed-text",
        alias="DASHBOARD_EMBED_MODEL",
    )

    embedding_batch_size: int = Field(default=100, alias="DASHBOARD_EMBEDDING_BATCH_SIZE")
    watcher_enabled: bool = Field(default=True, alias="DASHBOARD_WATCHER_ENABLED")

    # v1.1.2 Option A — how often the embeddings-promotion watchdog
    # re-probes Ollama when models aren't yet loaded (the cold-deploy
    # window where ollama-init is still pulling). Default 30s balances
    # responsiveness (dashboard goes fully online within ~30s of the
    # pull completing) against probe noise. Tune up on slow links.
    embeddings_promotion_interval_seconds: int = Field(
        default=30,
        alias="DASHBOARD_EMBEDDINGS_PROMOTION_INTERVAL_SECONDS",
        ge=5,
        le=600,
    )

    # Ingest gate — what gets embedded into Chroma. Three orthogonal knobs.
    # The operator-facing `/api/logs` view is UNAFFECTED by any of these
    # (it reads volumes directly, not Chroma).
    #
    # Phase 8 / ADR-017 — local embeddings are free, so the cost-driven
    # WARN+ERROR filter is rescinded. Default admits the full corpus
    # (DEBUG ∪ INFO ∪ WARN ∪ ERROR) so the agent gains baseline awareness
    # via RAG. Content-hash dedup in `upsert_entries` still avoids
    # redundant embedding work on restarts (performance benefit now,
    # not cost benefit).

    # `NoDecode` stops pydantic-settings from JSON-parsing the env value
    # before our `field_validator(mode="before")` gets to split the CSV.
    # Without it, langgraph 1.x's typing-extensions bump made pydantic-
    # settings try `json.loads("DEBUG,INFO,WARN,ERROR")` first and crash.
    dashboard_ingest_levels: Annotated[frozenset[LogLevel], NoDecode] = Field(
        default=frozenset({LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARN, LogLevel.ERROR}),
        alias="DASHBOARD_INGEST_LEVELS",
    )

    # Source filter — embed prod-, synthetic-, and unknown-tagged entries
    # by default. Source values come from each app's per-request middleware
    # via `structlog.contextvars` (SDA/FNOL), `AsyncLocalStorage` (CP), or
    # SLF4J `MDC` (AP), propagated cross-app via the outbound HTTP clients
    # forwarding `X-Source`. Vocabulary:
    #
    # "health"    → /health, /api/health, /actuator/health (parser-derived;
    #               immutable, header cannot override)
    # "test"      → Playwright suites (extraHTTPHeaders set X-Source: test);
    #               excluded by default so E2E noise stays out of Chroma
    # "synthetic" → Agitator-generated traffic (ADR-014); included
    # "prod"      → real-user traffic (React SPA fetch wrapper explicitly
    #               sets X-Source: prod per ADR-011 2026-06-07 amendment)
    # "unknown"   → middleware default when X-Source header is absent + parser
    #               fallback when no source field is present; admitted so the
    #               operator can spot leaks in propagation. Once the chain is
    #               rock-solid this should approach zero in Chroma.
    dashboard_ingest_sources: Annotated[frozenset[str], NoDecode] = Field(
        default=frozenset({"prod", "synthetic", "unknown"}),
        alias="DASHBOARD_INGEST_SOURCES",
    )

    # Dry-run mode — apply filters + parse, but DON'T call the embedder or
    # add to Chroma. Used to safely preview what the filter would pass
    # without disturbing the corpus. Backfill + watcher both honour it.
    dashboard_ingest_dry_run: bool = Field(
        default=False,
        alias="DASHBOARD_INGEST_DRY_RUN",
    )

    @field_validator("dashboard_ingest_levels", mode="before")
    @classmethod
    def _parse_ingest_levels(cls, value: object) -> object:
        if isinstance(value, str):
            return frozenset(v.strip().upper() for v in value.split(",") if v.strip())
        return value

    @field_validator("dashboard_ingest_sources", mode="before")
    @classmethod
    def _parse_ingest_sources(cls, value: object) -> object:
        if isinstance(value, str):
            return frozenset(v.strip().lower() for v in value.split(",") if v.strip())
        return value

    # LangSmith tracing — enabled when langsmith_api_key is a real value.
    # The lifespan sets LANGSMITH_TRACING=true at startup if so (LangChain's
    # auto-tracing also requires that env var, not just the API key).
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(
        default="agentic-log-analysis",
        alias="LANGSMITH_PROJECT",
    )

    # --- LangGraph agent + /api/chat (ADR-015, amended by ADR-017) ---
    #
    # Phase 8 / ADR-017 — runtime default flips to False. Local Ollama
    # removes the external-spend risk that drove Phase 7's safe-by-default
    # `True`. The DRY_RUN mechanism is preserved as a test-harness
    # convenience: an autouse fixture in `tests/conftest.py` forces it on
    # for the test scope so unit tests don't pay the 5-30s of local LLM
    # latency per call.
    dashboard_llm_dry_run: bool = Field(default=False, alias="DASHBOARD_LLM_DRY_RUN")

    # Per-request safety bounds — all enforced in-graph, deterministic.
    # Token cap uses `len(text) // 4` heuristic (post-Phase-8); rationale
    # is performance / UX bounding, not cost bounding.
    llm_max_tool_calls_per_request: int = Field(
        default=4, alias="DASHBOARD_LLM_MAX_TOOL_CALLS_PER_REQUEST", ge=1, le=20
    )
    llm_max_input_tokens_per_request: int = Field(
        default=8000, alias="DASHBOARD_LLM_MAX_INPUT_TOKENS_PER_REQUEST", ge=512, le=64_000
    )
    llm_max_messages_per_session: int = Field(
        default=40, alias="DASHBOARD_LLM_MAX_MESSAGES_PER_SESSION", ge=2, le=200
    )

    # Wall-clock cap on every Ollama HTTP call. Forwarded into
    # `ChatOllama(client_kwargs={"timeout": ...})` so it reaches both the
    # sync and async httpx clients (`langchain_ollama` has no `timeout`
    # field on the model itself — passing `timeout=` directly is silently
    # absorbed by pydantic `extra="allow"`).
    #
    # Default of 120 is sized empirically for cold-start on M1 Max
    # llama3.1:8b: the first agent-graph round after a container restart
    # loads the 8B weights into memory and routinely takes 60-100s. 30s
    # and 60s both false-fail cold-start chat. Operators with larger
    # models (planned qwen2.5:14b trial) or slower hardware can raise
    # this; the cap is 600s so a true Ollama hang still surfaces.
    llm_timeout_seconds: int = Field(
        default=120, alias="DASHBOARD_LLM_TIMEOUT_SECONDS", ge=5, le=600
    )

    # SessionIndex bounds the in-process LRU of `thread_id` checkpoints. When
    # the cap is hit, the oldest thread is evicted via `checkpointer.adelete_thread`.
    session_index_max: int = Field(
        default=200, alias="DASHBOARD_SESSION_INDEX_MAX", ge=10, le=10_000
    )

    # --- Proactive background scan + ERROR-tier chaos path (ADR-016, amended by ADR-017) ---
    #
    # The scan loop wakes on the configured interval, synthesises a "scan for
    # anomalies" prompt, invokes the SAME compiled LangGraph used by /api/chat,
    # and appends any non-NO_ANOMALIES result to an in-process ring buffer
    # surfaced via /api/status. Findings are restart-lossy by design (same
    # posture as RunRegistry).
    #
    # Real scans require BOTH `proactive_scan_enabled=True` AND
    # `dashboard_llm_dry_run=False`. Either alone is safe — dry-run makes the
    # loop log `proactive_scan_skipped reason=llm_dry_run` and continue
    # without invoking the LLM. Phase 7 rationale was cost-safety; Phase 8 /
    # ADR-017 rescinds that — the gate stays for noise control (the dry-run
    # fake returns the same canned answer every cycle).
    proactive_scan_enabled: bool = Field(default=False, alias="DASHBOARD_PROACTIVE_SCAN_ENABLED")
    proactive_scan_interval_seconds: int = Field(
        default=900,
        alias="DASHBOARD_PROACTIVE_SCAN_INTERVAL_SECONDS",
        ge=60,
        le=86_400,
    )
    proactive_scan_lookback_minutes: int = Field(
        default=30,
        alias="DASHBOARD_PROACTIVE_SCAN_LOOKBACK_MINUTES",
        ge=5,
        le=1440,
    )
    proactive_scan_max_findings: int = Field(
        default=5,
        alias="DASHBOARD_PROACTIVE_SCAN_MAX_FINDINGS",
        ge=1,
        le=20,
    )

    # --- Phase 7b: log ingestion ---

    # Mount root for the 4 read-only log volumes. Tests override to point at
    # tests/fixtures/logs/. Production is the docker-compose mount path.
    log_volume_root: Path = Field(
        default=Path("/mnt/logs"),
        alias="DASHBOARD_LOG_VOLUME_ROOT",
    )

    # How many lines to tail from each app per /api/logs (or /api/status) call.
    # 10k × 4 apps × ~200 bytes ≈ 8 MB scanned per request — fast and bounded.
    logs_tail_default: int = Field(default=10_000, alias="DASHBOARD_LOGS_TAIL_DEFAULT")
    logs_tail_max: int = Field(default=50_000, alias="DASHBOARD_LOGS_TAIL_MAX")

    # Max entries returned in one /api/logs response (after filtering + sort).
    # Caps the wire payload; UI uses next_before for further pages.
    logs_page_default: int = Field(default=100, alias="DASHBOARD_LOGS_PAGE_DEFAULT")
    logs_page_max: int = Field(default=1_000, alias="DASHBOARD_LOGS_PAGE_MAX")

    # --- PR 3 (Agitator): bundled load driver (ADR-014) ---
    # ENABLE_CHAOS is shared with the four monitored apps (their chaos
    # middleware also reads it). The dashboard reads it only to know whether
    # the sda-degraded scenario card should be enabled in the UI.
    enable_chaos: bool = Field(default=False, alias="ENABLE_CHAOS")

    # Global cap on the number of Agitator runs that may be `running` at once.
    # Keeps the bundled load driver from saturating the dashboard process.
    agitator_max_concurrent_runs: int = Field(
        default=2,
        alias="AGITATOR_MAX_CONCURRENT_RUNS",
        ge=1,
        le=10,
    )

    # Per-run socket concurrency cap (asyncio.Semaphore size). Scenarios
    # never open more than this many simultaneous sockets to a target.
    agitator_default_concurrency: int = Field(
        default=10,
        alias="AGITATOR_DEFAULT_CONCURRENCY",
        ge=1,
        le=100,
    )

    # Demo creds Agitator uses to log into FNOL/CP/AP at run start. Defaults
    # match seed data in apps/shared-data-api seed_data.py.
    agitator_customer_username: str = Field(
        default="alice",
        alias="AGITATOR_CUSTOMER_USERNAME",
    )
    agitator_customer_password: str = Field(
        default="customer",
        alias="AGITATOR_CUSTOMER_PASSWORD",
    )
    agitator_agent_username: str = Field(
        default="agent1",
        alias="AGITATOR_AGENT_USERNAME",
    )
    agitator_agent_password: str = Field(
        default="agent",
        alias="AGITATOR_AGENT_PASSWORD",
    )

    # Base URLs for the 4 target apps (compose service names, internal ports).
    shared_data_api_base_url: str = Field(
        default="http://shared-data-api:8000",
        alias="SHARED_DATA_API_BASE_URL",
    )
    fnol_base_url: str = Field(
        default="http://fnol-app:8000",
        alias="AGITATOR_FNOL_BASE_URL",
    )
    customer_portal_base_url: str = Field(
        default="http://customer-portal:3000",
        alias="AGITATOR_CP_BASE_URL",
    )
    agent_portal_base_url: str = Field(
        default="http://agent-portal:8080",
        alias="AGITATOR_AP_BASE_URL",
    )

    # CP's API key, reused for SDA-direct calls in the sda-degraded scenario.
    # Caller attribution will show as `caller=customer-portal` even though the
    # Agitator is the producer; the `source=synthetic` tag is the disambiguator.
    shared_data_api_key_customer_portal: str = Field(
        default="",
        alias="SHARED_DATA_API_KEY_CUSTOMER_PORTAL",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
