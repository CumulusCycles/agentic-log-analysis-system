# Project Rules — Logging Strategy

> **Canonical reference:** `docs/tech/logging-strategy.md` — full implementation details,
> code examples, and log level guidelines. This file is the compact runtime reference for
> Claude Code; the docs file governs when they conflict.

## Philosophy
Each app uses its native logging format. Do NOT normalize at write time.
The LangGraph agent handles heterogeneous formats. See docs/decisions/ADR-003-logging-strategy.md.

## Non-Negotiable Rule
Every app MUST log a parseable **severity level** and **timestamp**. Everything else is stack-native.

---

## Per-Stack Formats

### Shared Data API (Python / FastAPI)
- Library: Python `logging` + `structlog`
- Mix of structured JSON request logs and plain exception tracebacks
- Every request line includes `caller=<app>` (from `X-API-Key`) and `user=<id>` (from JWT) — the dashboard's primary correlation source
- Log file: `/app/logs/shared-data-api.log` → volume: `shared-data-api-logs`

### FNOL (Python / FastAPI)
- Library: Python `logging` + `structlog`
- Mix of structured JSON events and plain exception tracebacks
- Log file: `/app/logs/fnol-app.log` → volume: `fnol-logs`

### Customer Portal (Node.js / Express)
- Library: `winston` — structured JSON, one object per line
- Required fields: `level`, `message`, `timestamp`, `service`
- Log file: `/app/logs/customer-portal.log` → volume: `customer-portal-logs`

### Agent Portal (Java / Spring Boot)
- Library: Logback — `YYYY-MM-DD HH:mm:ss.SSS LEVEL --- [thread] class : message`
- Multi-line stack traces
- Log file: `/app/logs/agent-portal.log` → volume: `agent-portal-logs`

### Agentic Log Analysis Dashboard
- Own logs: stdout only — no log volume. Visible via `docker compose logs log-dashboard`.
- Consumes `shared-data-api-logs`, `fnol-logs`, `customer-portal-logs`, `agent-portal-logs` read-only. Never writes to log volumes.

---

## Volume Mount Paths

| App | Container path | Volume | Dashboard read path |
|---|---|---|---|
| Shared Data API | `/app/logs/shared-data-api.log` | `shared-data-api-logs` | `/mnt/logs/shared-data-api/shared-data-api.log` |
| FNOL | `/app/logs/fnol-app.log` | `fnol-logs` | `/mnt/logs/fnol/fnol-app.log` |
| Customer Portal | `/app/logs/customer-portal.log` | `customer-portal-logs` | `/mnt/logs/customer-portal/customer-portal.log` |
| Agent Portal | `/app/logs/agent-portal.log` | `agent-portal-logs` | `/mnt/logs/agent-portal/agent-portal.log` |

Dashboard mounts all four app log volumes **read-only**.
