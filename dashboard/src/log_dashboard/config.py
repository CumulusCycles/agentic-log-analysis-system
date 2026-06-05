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

    # Empty / placeholder string disables the embedding pipeline (search returns 503,
    # no ingestion). The dashboard MUST stay usable for /api/logs and /api/status
    # without an OpenAI key — see ADR-006 and the 7d plan's degraded-mode section.
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="OPENAI_EMBEDDING_MODEL",
    )
    # Defined in 7d for operator visibility; unused until 7e wires the LangGraph agent.
    openai_chat_model: str = Field(default="gpt-4o", alias="OPENAI_CHAT_MODEL")

    embedding_batch_size: int = Field(default=100, alias="DASHBOARD_EMBEDDING_BATCH_SIZE")
    watcher_enabled: bool = Field(default=True, alias="DASHBOARD_WATCHER_ENABLED")

    # Ingest gate — what gets embedded into Chroma. Three orthogonal knobs.
    # The operator-facing `/api/logs` view is UNAFFECTED by any of these
    # (it reads volumes directly, not Chroma).
    #
    # Defaults send only PROD WARN/ERROR to OpenAI — the smallest signal-rich
    # slice, minimal cost. Combine with `upsert_entries`' content-hash dedup
    # (Chroma is asked for existing IDs before any embed call) to ensure no
    # log line is ever embedded twice.

    # Level filter — drop everything below WARN by default.
    # `NoDecode` stops pydantic-settings from JSON-parsing the env value
    # before our `field_validator(mode="before")` gets to split the CSV.
    # Without it, langgraph 1.x's typing-extensions bump made pydantic-
    # settings try `json.loads("WARN,ERROR")` first and crash at startup.
    dashboard_ingest_levels: Annotated[frozenset[LogLevel], NoDecode] = Field(
        default=frozenset({LogLevel.WARN, LogLevel.ERROR}),
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
    # "prod"      → real-user traffic (default when no header is supplied)
    # "unknown"   → parser fallback when no source field is present; admitted
    #               so the operator can spot leaks in propagation. Once the
    #               chain is rock-solid this should approach zero in Chroma.
    dashboard_ingest_sources: Annotated[frozenset[str], NoDecode] = Field(
        default=frozenset({"prod", "synthetic", "unknown"}),
        alias="DASHBOARD_INGEST_SOURCES",
    )

    # Dry-run mode — apply filters + parse, but DON'T call the embedder or
    # add to Chroma. Used to safely preview what the filter would pass
    # without spending OpenAI tokens. Backfill + watcher both honour it.
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

    # --- Phase 7e (PR 4a): LangGraph agent + /api/chat ---
    #
    # `dashboard_llm_dry_run` defaults to True — safe-by-default. With dry-run on,
    # `analyze`/`predict` nodes use GenericFakeChatModel instead of ChatOpenAI;
    # no OpenAI call is ever made. Operator opts INTO paid spend by setting
    # DASHBOARD_LLM_DRY_RUN=false in `.env`. Cost-safety asymmetry: a forgotten
    # env var that defaults to spend is unrecoverable + pollutes LangSmith;
    # a forgotten env var that defaults to dry-run is a one-line `.env` edit.
    # Tests inherit dry-run automatically — the Settings default IS dry-run.
    dashboard_llm_dry_run: bool = Field(default=True, alias="DASHBOARD_LLM_DRY_RUN")

    # Cost-bounding caps — all enforced in-graph, deterministic, no advisory
    # middleware. Each is a single integer comparison.
    llm_max_tool_calls_per_request: int = Field(
        default=4, alias="DASHBOARD_LLM_MAX_TOOL_CALLS_PER_REQUEST", ge=1, le=20
    )
    llm_max_input_tokens_per_request: int = Field(
        default=8000, alias="DASHBOARD_LLM_MAX_INPUT_TOKENS_PER_REQUEST", ge=512, le=64_000
    )
    llm_max_messages_per_session: int = Field(
        default=40, alias="DASHBOARD_LLM_MAX_MESSAGES_PER_SESSION", ge=2, le=200
    )

    # SessionIndex bounds the in-process LRU of `thread_id` checkpoints. When
    # the cap is hit, the oldest thread is evicted via `checkpointer.adelete_thread`.
    session_index_max: int = Field(
        default=200, alias="DASHBOARD_SESSION_INDEX_MAX", ge=10, le=10_000
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
