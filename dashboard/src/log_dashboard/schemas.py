from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AdminOut(BaseModel):
    username: str
    role: str


class HealthResponse(BaseModel):
    status: str


# --- Phase 7b: log ingestion ---


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class LogEntry(BaseModel):
    """One parsed line from one of the four log volumes.

    `id` is `{app}:{sha1(raw)[:16]}` — content-stable across runs, set by the
    parser via `ingest.embeddings.make_doc_id`. Same identifier Chroma uses for
    the embedded document, which is what makes `GET /api/errors/{id}` a single
    O(1) Chroma metadata lookup (Phase 7e PR 4b). `fields` carries the
    heterogeneous structured payload (caller, user, method, path, status,
    duration_ms, claim_id, ...). `raw` preserves the original line so the
    Error Detail screen renders it verbatim.

    `source` tags the provenance of the line so the embedding pipeline can
    skip noise. Set by each app's request-logger middleware from the
    `X-Source` HTTP header per ADR-011 (default `prod`). The parser's
    `_infer_source` tags health-path requests as `health` first (an
    immutable property of the request that no header can override), then
    honours the explicit value, then defaults to `prod`.
    """

    id: str
    timestamp: datetime
    level: LogLevel
    app: str
    event: str
    fields: dict[str, Any] = Field(default_factory=dict)
    raw: str
    # ADR-011 2026-06-07 amendment: missing-source defaults to `unknown` so
    # the operator can spot propagation gaps. React SPAs explicitly tag
    # `prod` at their fetch wrapper; the parser sets `source` from the log
    # line. This schema default only fires when LogEntry is constructed
    # directly without a `source` arg (test fixtures, future call sites).
    source: str = "unknown"


class LogsResponse(BaseModel):
    entries: list[LogEntry]
    next_before: datetime | None = None


class LevelCounts(BaseModel):
    info: int = 0
    warn: int = 0
    error: int = 0


AppStatusKind = Literal["ok", "degraded", "error"]


class AppStatus(BaseModel):
    name: str
    status: AppStatusKind
    file_present: bool
    last_seen_at: datetime | None = None
    counts_1h: LevelCounts = Field(default_factory=LevelCounts)
    counts_24h: LevelCounts = Field(default_factory=LevelCounts)
    counts_7d: LevelCounts = Field(default_factory=LevelCounts)


class StatusResponse(BaseModel):
    as_of: datetime
    apps: list[AppStatus]
    # PR 3: True iff the Chroma vectorstore exists and has zero docs.
    # The Overview banner uses this to nudge the operator toward the
    # Log Generator on a fresh install. False when the vectorstore is
    # disabled (Ollama unreachable) or when count() is unavailable.
    corpus_empty: bool = False
    # PR 4c: proactive scan findings + loop status. The Overview page
    # renders `proactive_findings` (top-N newest first) inline above the
    # status grid. `scan_enabled` mirrors `DASHBOARD_PROACTIVE_SCAN_ENABLED`
    # so the UI knows whether to show an empty-state hint when no findings
    # exist yet. `last_scan_at` / `next_scan_at` are written by the scan
    # loop after each iteration. ProactiveFinding is defined later in the
    # module (PR 4c block); StatusResponse.model_rebuild() at the bottom
    # resolves the forward reference.
    proactive_findings: list["ProactiveFinding"] = Field(default_factory=list)
    scan_enabled: bool = False
    last_scan_at: datetime | None = None
    next_scan_at: datetime | None = None
    # v1.1.2 Option A — three-valued Ollama readiness so the frontend can
    # distinguish "models still pulling on a cold deploy" (transient, will
    # become ready) from "Ollama is unreachable" (operator config issue).
    # `"ready"` = backfill running / done; `"loading"` = ollama-init still
    # pulling, promotion watchdog re-probing; `"unreachable"` = daemon down
    # or URL wrong. The Log Explorer search 503 banner reads this field
    # to pick the right message.
    embeddings_state: Literal["ready", "loading", "unreachable"] = "ready"


# --- Phase 7d: semantic search ---


class LogsSearchRequest(BaseModel):
    """Semantic search over the Chroma-backed log embeddings."""

    query: str = Field(min_length=1, max_length=2000)
    apps: list[str] | None = None
    levels: list[LogLevel] | None = None
    since: datetime | None = None
    before: datetime | None = None
    top_k: int = Field(default=20, ge=1, le=200)


class LogsSearchResponse(BaseModel):
    entries: list[LogEntry]
    scores: list[float]
    # v1.1.2 — surface the partial-corpus window during initial backfill so
    # clients can distinguish "no results in a fully-populated corpus" from
    # "no results yet because Chroma is still being filled". Defaults False
    # so older clients ignoring the field see no change.
    partial_corpus: bool = False


# --- PR 3: Agitator ---


class ScenarioParamOut(BaseModel):
    name: str
    minimum: int
    maximum: int
    default: int


class ScenarioSpecOut(BaseModel):
    name: str
    display_name: str
    description: str
    target_app: str
    requires_chaos: bool
    params: list[ScenarioParamOut]


class AgitatorEnvOut(BaseModel):
    enable_chaos: bool


class RunCreateRequest(BaseModel):
    scenario: str
    params: dict[str, int] = Field(default_factory=dict)


RunState = Literal["running", "succeeded", "failed", "cancelled"]


class RunRecordOut(BaseModel):
    run_id: str
    scenario: str
    params: dict[str, int]
    state: RunState
    started_at: datetime
    ended_at: datetime | None = None
    sent: int = 0
    succeeded: int = 0
    failed: int = 0
    last_status_code: int | None = None
    last_error: str | None = None


class RunListResponse(BaseModel):
    runs: list[RunRecordOut]


# --- Phase 7e (PR 4a): LangGraph agent + /api/chat ---


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    """One turn in the chat history surfaced to the UI."""

    role: ChatRole
    content: str


class Citation(BaseModel):
    """A single log entry the agent cited as supporting evidence.

    Mirrors a subset of `LogEntry` plus the similarity `score`. The agent's
    `query_logs` tool sanitises `raw` via `credentials.sanitize_log_raw`
    BEFORE the citation reaches the LLM context, so this `raw` value is
    safe to ship to the client.
    """

    id: str
    timestamp: datetime
    level: LogLevel
    app: str
    event: str
    raw: str
    score: float


class ChatRequest(BaseModel):
    """Submit a question to the LangGraph agent.

    `session_id` is generated server-side on the first call (omit it). Echo
    it back on subsequent calls to share the InMemorySaver thread (carries
    conversation history). `streaming=true` (PR 4b) switches the response to
    Server-Sent Events — one `event: node` per agent node + one
    `event: complete` carrying the final answer + citations. Authentication,
    token-cap rejection, and other pre-flight errors return JSON in both
    modes so the client doesn't need an SSE parser to read `401 / 413 / 503`.
    """

    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    streaming: bool = False


class ChatResponse(BaseModel):
    """LangGraph agent's final answer + supporting citations.

    `dry_run` flips to True when `DASHBOARD_LLM_DRY_RUN=true` (Phase 8 /
    ADR-017 — runtime default is False; tests inherit True via an autouse
    fixture). The UI shows a banner in that case so the operator knows
    the answer came from `_DryRunChatModel`, not the real LLM.

    `tool_budget_exhausted` flips when the graph reached
    `llm_max_tool_calls_per_request` and was forced to short-circuit to
    `respond`. The final answer is still returned; this flag tells the UI
    to surface a caveat.
    """

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    session_id: str
    dry_run: bool = False
    tool_budget_exhausted: bool = False


# --- Phase 7e (PR 4b): Error Detail ---


class AgentAnalysis(BaseModel):
    """LangGraph agent's response when invoked on a single error.

    Same shape as `ChatResponse` minus the chat-specific `session_id` — the
    Error Detail flow mints an ephemeral session per click that the client
    cannot continue, so exposing it would be misleading. `dry_run` and
    `tool_budget_exhausted` carry forward so the UI can surface the same
    caveats it surfaces on chat.
    """

    answer: str
    citations: list[Citation] = Field(default_factory=list)
    dry_run: bool = False
    tool_budget_exhausted: bool = False


class ErrorDetailResponse(BaseModel):
    """`GET /api/errors/{id}` response.

    `entry` is the full log entry reconstructed from Chroma metadata —
    `raw` carries the original line so the UI doesn't need a second call.
    `analysis` is the agent's Suggested Fix.
    """

    entry: LogEntry
    analysis: AgentAnalysis


# --- Phase 7e (PR 4c): proactive background scan ---


ProactiveSeverity = Literal["info", "warn", "error"]


class ProactiveFinding(BaseModel):
    """One anomaly the proactive scan loop surfaced.

    `id` is `"proactive:{ulid}"` — opaque to the client; used as the React
    list key. `summary` is the sanitised final AIMessage from the agent.
    `severity` is derived deterministically from the cited entries' levels
    (any ERROR → error, else any WARN → warn, else info) — NOT from the LLM.
    `citations` reuses the PR 4a Citation type so a finding's links navigate
    to `/errors/:id` identically to a chat answer's citations. `dry_run` is
    True if the scan ran against `_DryRunChatModel`; today the loop skips
    invocation entirely when DRY_RUN=true, so this is always False, but the
    field is kept in the schema for the policy flip we may make later.
    """

    id: str
    scan_started_at: datetime
    scan_completed_at: datetime
    summary: str
    severity: ProactiveSeverity
    citations: list[Citation] = Field(default_factory=list)
    dry_run: bool = False


# Resolve the forward reference inside StatusResponse.proactive_findings now
# that ProactiveFinding is in module scope.
StatusResponse.model_rebuild()


# --- Phase 7+ post-Phase-7 polish: Overview trend charts (GET /api/status/history) ---


StatusHistoryWindow = Literal["1h", "24h", "7d"]


class StatusHistoryBucket(BaseModel):
    """One time bucket of per-level counts for one app."""

    ts: datetime  # bucket start (UTC, aligned to bucket boundary)
    info: int = 0
    warn: int = 0
    error: int = 0


class StatusHistoryResponse(BaseModel):
    """Per-app, per-bucket level counts for the requested window.

    `bucket_minutes` is fixed per window so the UI knows the bucket cadence
    without having to re-derive it. `apps` is a dict keyed by app name —
    same names as `StatusResponse.apps`. Each list is oldest-first
    (suitable for direct rendering as a left-to-right time series).
    """

    as_of: datetime
    window: StatusHistoryWindow
    bucket_minutes: int
    apps: dict[str, list[StatusHistoryBucket]]


# --- Vectorstore Stats tab — GET /api/chroma/stats ---


class DayCount(BaseModel):
    """One day's embedded-document count, UTC."""

    date: str  # "YYYY-MM-DD"
    count: int


class EventCount(BaseModel):
    """One row of the top-N event-name breakdown."""

    event: str
    count: int


class ChromaStatsResponse(BaseModel):
    """Aggregated stats over the Chroma collection — what's actually embedded.

    Computed in-process from a single `_collection.get(include=["metadatas"])`
    call; no LLM traffic. The shape is stable across empty + populated
    states so the UI can render the same scaffolding regardless. `as_of` is
    a single snapshot time — counts can shift between fields if ingestion
    is active during the request, but the jitter is acceptable for a stats
    tab.
    """

    total_count: int
    by_app: dict[str, int] = Field(default_factory=dict)
    by_level: dict[str, int] = Field(default_factory=dict)
    by_source: dict[str, int] = Field(default_factory=dict)
    by_event: list[EventCount] = Field(default_factory=list)  # top 10, descending
    by_day: list[DayCount] = Field(default_factory=list)  # last 30 days, ascending
    embedding_model: str
    dimensions: int
    as_of: datetime


class ChromaFlushResponse(BaseModel):
    """Result of POST /api/chroma/flush — wipes every doc in the collection.

    `deleted_count` is the doc count observed BEFORE the delete call. The
    operator-facing UI uses this to confirm "yes, N rows are gone." After
    flush, the collection still exists with the same name + embedding model;
    only the docs are gone (matches `chromadb` semantics). Repopulating
    requires `docker compose restart log-dashboard` — the lifespan's
    backfill task only runs at startup.
    """

    deleted_count: int
    as_of: datetime
