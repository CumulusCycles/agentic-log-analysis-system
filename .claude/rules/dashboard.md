# Project Rules — Agentic Log Analysis Dashboard

## Purpose
The primary deliverable. An agentic AI system that will continuously monitor logs from the
three logging apps (FNOL, Customer Portal, Agent Portal), identify issues, suggest
remediation, and proactively predict problems before they escalate.

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

---

## Agent Architecture (LangGraph StateGraph)
- **Nodes**: ingest → analyze → correlate → predict → respond
- **Tools**: `query_logs` (Chroma semantic search), `get_app_status`
- **Memory**: conversation history persisted per session
- **Proactive loop**: background run every N minutes, surfaces anomalies automatically

---

## UI Screens
- **Overview Dashboard**: per-app status cards, error counts (1h/24h/7d), recent anomalies
- **Log Explorer**: filter by app/severity/time, semantic search, paginated entries
- **AI Chat**: conversational interface for root cause + remediation
- **Error Detail**: full raw log, stack trace, LangGraph analysis panel, suggested fix

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
  - fnol-logs:/mnt/logs/fnol:ro
  - customer-portal-logs:/mnt/logs/customer-portal:ro
  - agent-portal-logs:/mnt/logs/agent-portal:ro
```

## Environment Variables
- `OPENAI_API_KEY`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `DASHBOARD_CHROMA_URL`

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

## Routes (Phase 7 — placeholder)

Backend API routes will be defined when the dashboard is scaffolded in Phase 7.
Required endpoints (derived from 4 UI screens):

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Container healthcheck |
| `GET` | `/api/status` | Per-app status cards for Overview Dashboard |
| `GET` | `/api/logs` | Paginated log entries for Log Explorer |
| `POST` | `/api/chat` | AI Chat — submit question, get LangGraph response |
| `GET` | `/api/errors/{id}` | Full error detail + LangGraph analysis |

---

## MCP Server Usage
See the MCP usage rule in `CLAUDE.md` — dashboard backend uses **docs-langchain**,
dashboard frontend uses **context7**.
