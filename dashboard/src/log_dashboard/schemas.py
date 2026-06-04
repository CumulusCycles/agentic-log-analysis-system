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
    skip noise. Today: "health" for /health requests, "prod" for everything
    else. Future: "test" once a cross-app PR adds X-Source header propagation
    through each app's request-logging middleware. Parsers default to "prod"
    but honour an explicit `source` field already in the log line.
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
