# Logging Strategy

## Philosophy

Each app logs in its native format. No normalization at write time.
The LangGraph agent in the dashboard handles heterogeneous formats via LLM understanding.
See `docs/decisions/ADR-003-logging-strategy.md`.

**Non-negotiable rule:** Every app MUST emit a parseable severity level and timestamp.
Everything else is stack-native.

---

## Per-Stack Implementation

### Shared Data API (Python / logging)

Logs to stdout only — no log file, no volume. Visible via `docker compose logs shared-data-api`.
Uses Python `logging` with INFO level. No structlog dependency.

---

### FNOL (Python / structlog + logging)

```python
import structlog
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("/app/logs/fnol-app.log"),
        logging.StreamHandler()
    ]
)
logger = structlog.get_logger()
```

Output: structured JSON events.

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

```xml
<appender name="FILE" class="ch.qos.logback.core.FileAppender">
  <file>/app/logs/agent-portal.log</file>
  <encoder>
    <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level --- [%thread] %-40logger{40} : %msg%n</pattern>
  </encoder>
</appender>
```

Output: `YYYY-MM-DD HH:mm:ss.SSS LEVEL --- [thread] class : message`. Multi-line stack traces.

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
| FNOL | `/app/logs/fnol-app.log` | `fnol-logs` | `/mnt/logs/fnol/fnol-app.log` |
| Customer Portal | `/app/logs/customer-portal.log` | `customer-portal-logs` | `/mnt/logs/customer-portal/customer-portal.log` |
| Agent Portal | `/app/logs/agent-portal.log` | `agent-portal-logs` | `/mnt/logs/agent-portal/agent-portal.log` |

Dashboard mounts all three volumes **read-only**. It never writes to log volumes.

---

## Agentic Log Analysis Dashboard

The dashboard is a log consumer, not a log producer in the traditional sense.

- **Own logs:** stdout only (no log volume, no file). Visible via `docker compose logs log-dashboard`.
- **Consumed logs:** mounts `fnol-logs`, `customer-portal-logs`, and `agent-portal-logs` read-only at `/mnt/logs/<app>/`. A `watchdog` file watcher detects new entries and streams them to Chroma.
- The dashboard does not normalize incoming log formats — the LangGraph agent interprets heterogeneous formats at query time.