from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    dashboard_ingest_levels: frozenset[LogLevel] = Field(
        default=frozenset({LogLevel.WARN, LogLevel.ERROR}),
        alias="DASHBOARD_INGEST_LEVELS",
    )

    # Source filter — only embed prod-tagged entries by default.
    # "health" → /health, /api/health, /actuator/health (parser detects)
    # "test"   → reserved for a future cross-app X-Source header PR
    # "prod"   → everything else (parser default)
    dashboard_ingest_sources: frozenset[str] = Field(
        default=frozenset({"prod"}),
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
