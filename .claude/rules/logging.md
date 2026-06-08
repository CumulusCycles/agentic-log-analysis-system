# Project Rules — Logging Strategy

> **Canonical reference:** `docs/tech/logging-strategy.md` — full implementation details,
> code examples, and log level guidelines. This file is the compact runtime reference for
> Claude Code; the docs file governs when they conflict.

## Philosophy
Each app uses its native logging format. Do NOT normalize at write time.
The LangGraph agent handles heterogeneous formats. See docs/decisions/ADR-003-logging-strategy.md.

## Non-Negotiable Rules

1. Every app MUST log a parseable **severity level** and **timestamp**. Everything else is stack-native.

   Every per-request log line MUST also include a `source=<value>` field
   read from the `X-Source` HTTP header (default `unknown` — ADR-011
   2026-06-07 amendment). React SPAs explicitly tag `X-Source: prod` in
   their `request()` fetch wrapper so real UX traffic lands in `prod`;
   anything missing the header lands in `unknown` as a propagation-gap
   signal. Domain events (`login_failed`, `sda_upstream_rejected`, etc.)
   emitted during the request lifetime MUST also carry the same `source`
   value, propagated via the stack-native carrier set by the request
   middleware: `structlog.contextvars` (SDA, FNOL), `AsyncLocalStorage`
   (CP), SLF4J `MDC` (AP). Outbound HTTP clients to SDA MUST forward
   `X-Source` from the same carrier so SDA tags its WARN/ERROR events
   with the original source instead of defaulting to `unknown`. Domain
   events emitted OUTSIDE a request context (startup, background tasks)
   get tagged `unknown` so the operator can spot propagation gaps.

2. **NEVER LOG CREDENTIALS — ABSOLUTE PROHIBITION.** The following values MUST NEVER appear in any log line, structured field, error message, exception trace, response body, or debug output across any app:
   - Passwords (plain, hashed, or any intermediate form)
   - JWT secrets / signing keys (`JWT_SECRET`, `DASHBOARD_JWT_SECRET`)
   - API keys (`SHARED_DATA_API_KEY_*`)
   - Bearer tokens, full JWTs, or any token segment
   - DB credentials (`POSTGRES_PASSWORD`, `MONGO_INITDB_ROOT_PASSWORD`, full connection strings with `user:pass@host`)
   - LLM API keys (`OPENAI_API_KEY` — removed in PR 8b per ADR-017 Phase 8 / Ollama migration; `LANGSMITH_API_KEY` — stays)
   - Admin credentials (`DASHBOARD_ADMIN_PASSWORD`)
   - **Any other value defined in `.env` or `.env.example` that maps to a real secret**

   Why: logs are aggregated, persisted to volumes, ingested by the dashboard (Phase 7+), embedded in a vector store via OpenAI's API, traced through LangSmith, and may be screenshotted or pasted into PR comments. Any one of those becomes a credential leak the moment a secret crosses the log boundary.

   What IS safe to log: identifiers (`user_id`, `username`, `policy_number`, `claim_id`, `caller`), decoder error messages (`reason="Signature verification failed"`), and outcomes (`status`, `duration_ms`). Use identifiers and outcomes, never the secret values themselves.

   Audit baseline (verified 2026-06-04): every logger call site in SDA, FNOL, CP, AP scanned and confirmed clean. Preserve this state in every PR that touches logging.

   Phase 7e (PR 4a, 2026-06-05): user input and tool-returned log lines pass through `dashboard/src/log_dashboard/credentials.py` before reaching LangChain / LangSmith / OpenAI. Two-layer defence (input sanitisation in `routers/chat.py` + `agent/nodes.py::ingest_node`; output sanitisation in `agent/tools.py::query_logs`). Verified via `test_credentials.py` + `test_agent_credential_redaction.py`. Shared shape detection (JWT pattern + sensitive-keyword vocabulary) lives in `dashboard/src/log_dashboard/credential_patterns.py` (post-Phase-7 dedup chore, 2026-06-07) — `credentials.py` and `agitator/runs.py::_sanitize_error` import from there so the two cannot drift; each consumer keeps its own policy (surgical substitute vs. drop whole message).

   Full decision tree and counter-patterns: `feedback_never_log_credentials` memory file (auto-loaded).

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
