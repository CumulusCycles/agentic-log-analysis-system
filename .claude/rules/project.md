# Project Rules — Architecture & Structure

## What This Project Is

A locally-run insurance application ecosystem consisting of four supporting apps,
two databases, and a log analysis dashboard — all running across 8 containers
orchestrated via Docker Compose.

The primary deliverable is the **log analysis dashboard**. All four apps log during normal
operation. The Shared Data API, FNOL, Customer Portal, and Agent Portal each write to their
own mounted volume; the dashboard reads all four read-only.

The Shared Data API is the sole data-access layer (Mongo + Postgres). FNOL, Customer Portal,
and Agent Portal have no direct DB driver — they call the Shared Data API over HTTP.
Customer Portal and Agent Portal are read-only by design; FNOL is the sole write path.
See ADR-005, ADR-006, ADR-007, and `docs/tech/data-model.md`.

---

## Repo Structure

```
agentic-log-analysis-system/
├── CLAUDE.md
├── CLAUDE_RESOURCES.md
├── PLAN.md
├── LICENSE
├── docker-compose.yml
├── .env.example
├── .gitattributes
├── .gitignore
├── .mcp.json
├── .claude/
│   ├── settings.json
│   ├── settings.local.json   (local, gitignored)
│   ├── rules/
│   ├── agents/
│   ├── commands/
│   ├── hooks/
│   └── skills/
├── apps/
│   ├── shared-data-api/
│   ├── fnol/
│   ├── customer-portal/
│   └── agent-portal/
├── dashboard/
└── docs/
    ├── README.md
    ├── project-brief.md
    ├── development-workflow.md
    ├── architecture/
    ├── tech/
    │   ├── file-naming-convention.md
    │   ├── logging-strategy.md
    │   └── tech-stack.md
    └── decisions/
```

---

## The Four Applications

| App | Stack | Data | Users |
|---|---|---|---|
| Shared Data API | Python / FastAPI (API only) | PostgreSQL + MongoDB (sole owner of both) | All apps (sole data-access layer) |
| FNOL | Python / FastAPI + React | Via Shared Data API (HTTP) — no direct DB | Policyholders at accident scene (mobile) — JWT login |
| Customer Portal | Node / Express + React | Via Shared Data API (HTTP, read-only) — no direct DB | Policyholders managing policies (desktop) — JWT login |
| Agent Portal | Java / Spring Boot + React | Via Shared Data API (HTTP, read-only) — no direct DB | Internal claim handlers (desktop) — JWT login |

All four apps require login. Dashboard auth is standalone (env-supplied admin); the three insurance apps share a JWT secret issued by the Shared Data API. See ADR-006.

---

## Infrastructure

| Container | Role |
|---|---|
| `shared-data-api` | Customer/policy data service |
| `fnol-app` | FNOL submission app |
| `customer-portal` | Customer self-service app |
| `agent-portal` | Agent / claim handler app |
| `log-dashboard` | Agentic Log Analysis Dashboard |
| `postgres` | Shared relational DB |
| `mongodb` | Document DB (owned by Shared Data API — users + policies) |
| `chroma` | Vector store (log embeddings for dashboard) |

---

## Persistent Volumes

| Volume | Purpose |
|---|---|
| `postgres-data` | PostgreSQL app data |
| `mongodb-data` | MongoDB app data |
| `shared-data-api-logs` | Shared Data API application logs |
| `fnol-logs` | FNOL application logs |
| `customer-portal-logs` | Customer Portal logs |
| `agent-portal-logs` | Agent Portal logs |
| `chroma-data` | Chroma vector store data |

---

## Phase Scope

### Phases 1–2 — Scaffold & Infrastructure
- Repo skeleton, Claude Code config, docs
- Docker Compose: all 8 containers, 6 volumes, healthchecks, ARM64 platform flags (the 7th log volume `shared-data-api-logs` was added in Pre-Phase-3 — see below)

### Pre-Phase-3 — Architecture Pivot (docs only)
- Shared Data API becomes sole data-access layer; CP/AP read-only; JWT + per-app API keys; background claim-status simulator; 7th log volume `shared-data-api-logs`. See ADR-005, ADR-006, ADR-007.

### Phases 3–6 — Build & Instrument
- Scaffold all apps with realistic insurance functionality
- Natural log generation from normal app operation

### Phase 7 — Agentic Log Analysis Dashboard
Decomposed into 5 sub-PRs with the LLM work deferred (memory:
`project_phase_7_subpr_sequence`):
- **7a** — Scaffold + standalone JWT auth (FastAPI + React + container)
- **7b** — Log ingestion (read 4 volumes, parse native formats, `/api/logs` + `/api/status`)
- **7c** — UI for Overview + Log Explorer (no LLM)
- **7d** — Chroma + embeddings pipeline (semantic search; no LLM analysis yet)
- **7e** — LangGraph agent (analyze → correlate → predict → respond) + AI Chat + Error Detail
