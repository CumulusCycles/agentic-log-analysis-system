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

    `id` is `{app}:{seq}` where seq is monotonic within one /api/logs response.
    `fields` carries the heterogeneous structured payload (caller, user, method,
    path, status, duration_ms, claim_id, ...). `raw` preserves the original
    line so the future Error Detail screen (7e) can render it verbatim.

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
    source: str = "prod"


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
    # disabled (no OpenAI key) or when count() is unavailable.
    corpus_empty: bool = False


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
    conversation history). `streaming=true` is rejected with 422 in PR 4a —
    the field exists so the contract is forward-compatible with SSE in 4b.
    """

    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    streaming: bool = False
    # Streaming rejection is enforced in `routers/chat.py` via HTTPException(422)
    # instead of a model_validator — the validator's ValueError lands in the
    # validation handler's `ctx` field, which can't be JSON-serialised.


class ChatResponse(BaseModel):
    """LangGraph agent's final answer + supporting citations.

    `dry_run` flips to True when `DASHBOARD_LLM_DRY_RUN=true` (the default —
    safe-by-default). The UI shows a banner in that case so the operator
    knows the answer came from `GenericFakeChatModel`, not OpenAI.

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
