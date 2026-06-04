# Project Rules — Agentic Log Analysis Dashboard

## Purpose
The primary deliverable. An agentic AI system that will continuously monitor logs from all
four logging apps (Shared Data API, FNOL, Customer Portal, Agent Portal), identify issues,
suggest remediation, and proactively predict problems before they escalate.

---

## Stack
- **Backend**: Python 3.12 / FastAPI (`uv`)
- **Frontend**: React 18 + Vite + TypeScript (`pnpm`)
- **AI Framework**: LangChain + LangGraph
- **LLM**: OpenAI (`gpt-4o` for analysis, `text-embedding-3-small` for embeddings)
- **Vector Store**: Chroma (persistent Docker container)
- **Observability**: LangSmith (trace every agent run)
- **Log ingestion**: `watchdog` file watcher → embeds entries into Chroma continuously
- **Single container**: FastAPI serves React build as static files
- **Standalone auth**: local JWT signed with `DASHBOARD_JWT_SECRET`; admin credentials from env (`DASHBOARD_ADMIN_USERNAME` / `DASHBOARD_ADMIN_PASSWORD`). Independent of the Shared Data API — the dashboard must function for diagnostics when SDA is down. See ADR-006.

---

## Agent Architecture (LangGraph StateGraph)
- **Nodes**: ingest → analyze → correlate → predict → respond
- **Tools**: `query_logs` (Chroma semantic search), `get_app_status`
- **Memory**: conversation history persisted per session
- **Proactive loop**: background run every N minutes, surfaces anomalies automatically

---

## UI Screens
- **Overview Dashboard** (7c ✅): per-app status cards (ok / degraded / error), 1h/24h/7d INFO/WARN/ERROR counts, polled every 15 s; click a card to drill down to the Log Explorer pre-filtered to that app.
- **Log Explorer** (7c ✅): paginated/filterable log table (app, level, time-window preset 1h/24h/7d), row click expands `fields` + raw line inline, `next_before` cursor pagination. Semantic search is deferred to 7d.
- **AI Chat** (7e): conversational interface for root cause + remediation
- **Error Detail** (7e): full raw log, stack trace, LangGraph analysis panel, suggested fix

---

## Container Config
- Service name: `log-dashboard` · Internal port: 4000 / Host port: 4001
- Health endpoint: `GET /health` · Platform: `linux/arm64`
- Depends on: `chroma` (service_healthy)

## Chroma Container Config
- Service name: `chroma` · Image: `chromadb/chroma:1.5.9`
- Internal port: 8000 (internal only — not exposed to host)
- Volume: `chroma-data:/chroma/chroma`
- Env: `IS_PERSISTENT=TRUE`, `PERSIST_DIRECTORY=/chroma/chroma`

---

## Volume Access — READ-ONLY
```yaml
volumes:
  - shared-data-api-logs:/mnt/logs/shared-data-api:ro
  - fnol-logs:/mnt/logs/fnol:ro
  - customer-portal-logs:/mnt/logs/customer-portal:ro
  - agent-portal-logs:/mnt/logs/agent-portal:ro
```

## Environment Variables
- `OPENAI_API_KEY`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `DASHBOARD_CHROMA_URL`
- `DASHBOARD_JWT_SECRET`, `DASHBOARD_ADMIN_USERNAME`, `DASHBOARD_ADMIN_PASSWORD` (standalone auth)

---

## Directory Layout
```
dashboard/
├── main.py              # FastAPI entry point
├── pyproject.toml       # Python deps (uv)
├── tests/               # pytest test suite
└── frontend/            # React + Vite + TypeScript (pnpm)
    ├── package.json
    └── src/
```
Backend (`uv run pytest`) runs from `dashboard/`.
Frontend (`pnpm test`) runs from `dashboard/frontend/`.

---

## Routes

Phase 7 is sub-PR'd into 5 slices (memory: `project_phase_7_subpr_sequence`).
Routes land incrementally:

| Method | Path | Purpose | Phase |
|---|---|---|---|
| `GET` | `/health` | Container healthcheck | 7a ✅ |
| `POST` | `/api/auth/login` | Admin login → JWT (standalone, independent of SDA) | 7a ✅ |
| `GET` | `/api/auth/me` | Current admin from JWT | 7a ✅ |
| `GET` | `/api/status` | Per-app status cards for Overview Dashboard | 7b ✅ |
| `GET` | `/api/logs` | Paginated log entries for Log Explorer | 7b ✅ |
| `POST` | `/api/logs/search` | Semantic search over Chroma — body: query + filter clauses; returns LogEntry[] + scores | 7d ✅ |
| `POST` | `/api/chat` | AI Chat — submit question, get LangGraph response | 7e |
| `GET` | `/api/errors/{id}` | Full error detail + LangGraph analysis | 7e |

Swagger UI (`/docs`, `/redoc`, `/openapi.json`) is exposed — the dashboard's
audience is the admin/operator, and Swagger is a strict diagnostic win.
Anonymous browser load mirrors SDA; calling endpoints still requires JWT via
the Authorize button. ADR-001 local-only threat model applies.

> Dashboard auth does NOT depend on the Shared Data API being healthy — by design.
> Local-only JWT keeps the diagnostic tool usable when the apps it observes are sick.

---

## Ingest Gate (Phase 7d)

Backfill + watcher both apply a 3-knob filter BEFORE any OpenAI embedding call.
The operator-facing `/api/logs` view reads volumes directly and is UNAFFECTED.

| Knob | Default | Where set |
|---|---|---|
| `DASHBOARD_INGEST_LEVELS` | `WARN,ERROR` | `.env` (CSV) |
| `DASHBOARD_INGEST_SOURCES` | `prod` | `.env` (CSV) |
| `DASHBOARD_INGEST_DRY_RUN` | `false` | `.env` (bool) |

`source` is set by the apps' request-logger middleware from the `X-Source`
header (default `prod`) per ADR-011. The parser's `_infer_source` precedence:
- `event=request` with path in `(/health, /api/health, /actuator/health)` → `source="health"` (beats explicit — path cannot be overridden by a header)
- Explicit `source=<value>` in the log line → honored
- Otherwise → `source="prod"`

Allowed vocabulary: `prod` (default), `synthetic` (Agitator, PR 3), `test`
(Playwright `extraHTTPHeaders`), `health` (parser-derived).

The default `(level ∈ {WARN, ERROR}) AND (source = prod)` predicate keeps healthcheck heartbeat, INFO business events, and Playwright E2E traffic out of Chroma — sharp signal, ~$0 ongoing cost.

`DASHBOARD_INGEST_DRY_RUN=true` makes `upsert_entries` short-circuit before any embedder call — operator-safe preview of what the filter would pass without spending tokens. Backfill + watcher still log `parsed`, `passed_filter`, `embedded` so the filter behavior is visible.

Cost-saver gate: `upsert_entries` queries Chroma for existing IDs (`store._collection.get(ids=..., include=[])`) BEFORE the embedder is called. Content-hash IDs (`{app}:{sha1(raw)[:16]}`) make restarts against a populated Chroma volume cost $0.

---

## MCP Server Usage
See the MCP usage rule in `CLAUDE.md` — dashboard backend uses **docs-langchain**,
dashboard frontend uses **context7**.
