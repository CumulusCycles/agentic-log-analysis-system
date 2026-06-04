"""Registry of the four log volumes the dashboard reads.

The volume mount paths are defined in `docker-compose.yml` (see PR #24's
log-dashboard service) and the per-app format in `.claude/rules/logging.md`.
This module keeps both in one place so adding a future producer means one
edit, not a scavenger hunt.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class LogFormat(str, Enum):
    """Native log format per app — drives parser dispatch."""

    STRUCTLOG_JSON = "structlog_json"  # SDA + FNOL (Python structlog + ProcessorFormatter)
    WINSTON_JSON = "winston_json"  # CP (Node.js winston)
    LOGBACK_TEXT = "logback_text"  # AP (Java Logback pattern)


@dataclass(frozen=True)
class AppLog:
    """One log producer the dashboard consumes."""

    name: str  # "shared-data-api" | "fnol" | "customer-portal" | "agent-portal"
    relative_path: str  # path under the volume root, e.g. "shared-data-api/shared-data-api.log"
    fmt: LogFormat

    def absolute_path(self, volume_root: Path) -> Path:
        return volume_root / self.relative_path


# Canonical registry — the order is the display order on the Overview screen (7c).
APP_LOGS: tuple[AppLog, ...] = (
    AppLog(
        name="shared-data-api",
        relative_path="shared-data-api/shared-data-api.log",
        fmt=LogFormat.STRUCTLOG_JSON,
    ),
    AppLog(name="fnol", relative_path="fnol/fnol-app.log", fmt=LogFormat.STRUCTLOG_JSON),
    AppLog(
        name="customer-portal",
        relative_path="customer-portal/customer-portal.log",
        fmt=LogFormat.WINSTON_JSON,
    ),
    AppLog(
        name="agent-portal",
        relative_path="agent-portal/agent-portal.log",
        fmt=LogFormat.LOGBACK_TEXT,
    ),
)

APP_LOG_BY_NAME: dict[str, AppLog] = {al.name: al for al in APP_LOGS}
APP_NAMES: frozenset[str] = frozenset(al.name for al in APP_LOGS)
