# Logging Strategy

## Philosophy

Each app logs in its native format. No normalization at write time.
The LangGraph agent in the dashboard handles heterogeneous formats via LLM understanding.
See `docs/decisions/ADR-003-logging-strategy.md`.

**Non-negotiable rule:** Every app MUST emit a parseable severity level and timestamp.
Everything else is stack-native.

---

## Per-Stack Implementation

### Shared Data API (Python / structlog + logging)

```python
import structlog
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("/app/logs/shared-data-api.log"),
        logging.StreamHandler()
    ]
)
logger = structlog.get_logger()
```

Output: structured JSON events. Every request log line includes `caller=<app>` and
`user=<id>` for dashboard correlation — caller comes from the `X-API-Key` header
(see ADR-006), user from the JWT subject.

> **structlog configuration note:** the Shared Data API sets
> `cache_logger_on_first_use=False`. Module-level `log = get_logger(__name__)`
> calls would otherwise lock in whatever config existed at first use, which
> breaks both `structlog.testing.capture_logs()` in tests and live
> reconfiguration. Do not flip this back to `True` without a corresponding
> refactor to fetch loggers inside functions.

---

### FNOL (Python / structlog + logging)

Same `structlog` ProcessorFormatter bridge pattern as the Shared Data API — JSON
to `sys.stdout` and to a `RotatingFileHandler` writing `/app/logs/fnol-app.log`
(volume `fnol-logs`, 10 MB × 5 rotations). Configured via
`apps/fnol/src/fnol/logging_setup.py:configure_logging()` and must keep
`cache_logger_on_first_use=False` — same trap as the SDA.

Output: one JSON object per line. Every request emits a line from
`RequestLoggerMiddleware` with `caller="-"` (FNOL is the edge — no upstream caller),
`user=<jwt.user_id>`, `method`, `path`, `status`, `duration_ms`.

```python
from fnol.logging_setup import configure_logging, get_logger
configure_logging("/app/logs/fnol-app.log")
log = get_logger(__name__)
log.info("startup_complete")
```

### Customer Portal (Node.js / winston)

```js
const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  defaultMeta: { service: 'customer-portal' },
  transports: [
    new winston.transports.File({ filename: '/app/logs/customer-portal.log' }),
    new winston.transports.Console()
  ]
});
```

Output: one JSON object per line. Required fields: `level`, `message`, `timestamp`, `service`.

### Agent Portal (Java / Logback)

Actual config in `apps/agent-portal/src/main/resources/logback-spring.xml` uses a `RollingFileAppender` with `SizeAndTimeBasedRollingPolicy` (10 MB max, 5 files history, 100 MB total cap):

```xml
<appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
  <file>/app/logs/agent-portal.log</file>
  <encoder>
    <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level --- [%thread] %logger : %msg%n</pattern>
  </encoder>
  <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
    <fileNamePattern>/app/logs/agent-portal.log.%d{yyyy-MM-dd}.%i.gz</fileNamePattern>
    <maxFileSize>10MB</maxFileSize>
    <maxHistory>5</maxHistory>
    <totalSizeCap>100MB</totalSizeCap>
  </rollingPolicy>
</appender>
```

Output: `YYYY-MM-DD HH:mm:ss.SSS LEVEL --- [thread] class : message`. Per-request lines from `RequestLoggingFilter` follow the shape `request method=<m> path=<p> caller=- user=<jwt user_id|-> status=<s> duration_ms=<n>` so the dashboard's heterogeneous-format parser can correlate against SDA's structured JSON. Multi-line stack traces use Logback's native formatting.

---

## Log Levels — When to Use Each

| Level | When |
|---|---|
| `INFO` | Normal operations — request received, record created, seed data loaded |
| `WARN` | Recoverable issues — duplicate detected, validation failed, session expired |
| `ERROR` | Something actually failed — DB unreachable, unhandled exception, external call failed |

Do not emit ERROR for conditions that are handled and recovered. Do not suppress errors silently.

---

## Volume Mount Paths

| App | Container log path | Docker volume | Dashboard mount |
|---|---|---|---|
| Shared Data API | `/app/logs/shared-data-api.log` | `shared-data-api-logs` | `/mnt/logs/shared-data-api/shared-data-api.log` |
| FNOL | `/app/logs/fnol-app.log` | `fnol-logs` | `/mnt/logs/fnol/fnol-app.log` |
| Customer Portal | `/app/logs/customer-portal.log` | `customer-portal-logs` | `/mnt/logs/customer-portal/customer-portal.log` |
| Agent Portal | `/app/logs/agent-portal.log` | `agent-portal-logs` | `/mnt/logs/agent-portal/agent-portal.log` |

Dashboard mounts all four volumes **read-only**. It never writes to log volumes.

---

## Agentic Log Analysis Dashboard

The dashboard is a log consumer, not a log producer in the traditional sense.

- **Own logs:** stdout only (no log volume, no file). Visible via `docker compose logs log-dashboard`.
- **Consumed logs:** mounts `shared-data-api-logs`, `fnol-logs`, `customer-portal-logs`, and `agent-portal-logs` read-only at `/mnt/logs/<app>/`. A `watchdog` file watcher detects new entries and streams them to Chroma.
- The dashboard does not normalize incoming log formats — the LangGraph agent interprets heterogeneous formats at query time.