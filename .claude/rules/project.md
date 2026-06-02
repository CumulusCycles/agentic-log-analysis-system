# Project Rules — Architecture & Structure

## What This Project Is

A locally-run insurance application ecosystem consisting of four supporting apps,
two databases, and a log analysis dashboard — all running across 8 containers
orchestrated via Docker Compose.

The primary deliverable is the **log analysis dashboard**. The four apps will log during
normal operation; FNOL, Customer Portal, and Agent Portal will write to mounted volumes that
the dashboard will analyze (Shared Data API logs to stdout only).

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

| App | Stack | DB | Users |
|---|---|---|---|
| Shared Data API | Python / FastAPI (API only) | PostgreSQL | All apps (customer/policy data service) |
| FNOL | Python / FastAPI + React | PostgreSQL (direct, own tables) + Shared Data API (HTTP, customer/policy lookups) | Policyholders at accident scene (mobile) |
| Customer Portal | MERN | MongoDB | Policyholders managing policies (desktop) |
| Agent Portal | Java / Spring Boot + React | PostgreSQL | Internal claim handlers (desktop) |

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
| `mongodb` | Document DB (Customer Portal only) |
| `chroma` | Vector store (log embeddings for dashboard) |

---

## Persistent Volumes

| Volume | Purpose |
|---|---|
| `postgres-data` | PostgreSQL app data |
| `mongodb-data` | MongoDB app data |
| `fnol-logs` | FNOL application logs |
| `customer-portal-logs` | Customer Portal logs |
| `agent-portal-logs` | Agent Portal logs |
| `chroma-data` | Chroma vector store data |

---

## Phase Scope

### Phases 1–2 — Scaffold & Infrastructure
- Repo skeleton, Claude Code config, docs
- Docker Compose: all 8 containers, 6 volumes, healthchecks, ARM64 platform flags

### Phases 3–6 — Build & Instrument
- Scaffold all apps with realistic insurance functionality
- Natural log generation from normal app operation

### Phase 7 — Agentic Log Analysis Dashboard
- LangChain + LangGraph + OpenAI integration
- Continuous log ingestion into Chroma vector store
- LangGraph agent: analyze → correlate → predict → remediate
- Proactive anomaly detection and conversational UI
