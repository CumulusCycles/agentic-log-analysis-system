# Agentic Log Analysis System

![ci](https://img.shields.io/github/actions/workflow/status/CumulusCycles/agentic-log-analysis-system/ci.yml?branch=main&label=ci)

![License](https://img.shields.io/badge/license-MIT-yellow) ![Platform](https://img.shields.io/badge/platform-linux%2Farm64-blue)

An AI-powered log management platform built on a realistic insurance application ecosystem.
Four full-stack apps generate heterogeneous logs in their native formats; a LangGraph + OpenAI
dashboard continuously monitors, correlates, and explains them.

The supporting apps are the raw material. **The dashboard is the product.**

---

## Architecture

| App | Stack | Purpose |
|---|---|---|
| **Shared Data API** | Python / FastAPI | Sole data-access layer (Mongo + Postgres) — all customer/policy/claim reads, FNOL writes, issues JWTs, runs claim-status simulator (no UI) |
| **FNOL** | Python / FastAPI + React | First Notice of Loss — sole write path for claims (mobile) |
| **Customer Portal** | Node / Express + React | Policyholder self-service — **read-only** view (desktop) |
| **Agent Portal** | Java / Spring Boot + React | Internal claim handler tool — **read-only** view (desktop) |
| **Agentic Log Analysis Dashboard** | Python / FastAPI + React + LangGraph | Agentic log analysis — the primary deliverable |

Infrastructure: PostgreSQL · MongoDB · Chroma vector store · Docker Compose · `insurance-net` bridge network

Auth: JWT issued by Shared Data API for FNOL / Customer Portal / Agent Portal; standalone JWT for the Dashboard. See [ADR-006](docs/decisions/ADR-006-auth-strategy.md).

---

## Status

Phases 1 through 7 are complete. The build sequence — including the Agitator series and the Phase 7e LangGraph slice — is logged in [`PLAN.md`](PLAN.md).

---

## Prerequisites

| Tool | Version | Used For |
|---|---|---|
| Docker Desktop | Latest | All containers (allocate ≥ 20 GB RAM, 8 CPUs on M1 Max) |
| `pnpm` | 9+ | Node/React apps and dashboard frontend |
| `uv` | Latest | Python apps (Shared Data API, FNOL, Agentic Log Analysis Dashboard backend) |
| Java | 21 | Agent Portal |
| Maven | 3.9+ | Agent Portal build |
| OpenAI API key | — | Dashboard LLM and embeddings |
| LangSmith account | — | Agent observability |

---

## Quick Start

```bash
# 1. Copy the environment template and fill in your values
cp .env.example .env

# 2. Build and start all services in the background
docker compose up -d

# 3. Verify every container is running and healthy
docker compose ps
```

### Service endpoints

After `docker compose up -d`, click the link to verify the corresponding container is responding.

Each app row links the three conceptual endpoints where they apply:
**`health`** (Docker probe), **`docs`** (Swagger UI — SDA + Dashboard), **`ux`** (browser UI).

| Container | health | docs | ux |
|---|---|---|---|
| Shared Data API | [health](http://localhost:8002/health) | [docs](http://localhost:8002/docs) | — (API only) |
| FNOL | [health](http://localhost:8001/health) | — | [ux](http://localhost:8001/) (mobile-first) |
| Customer Portal | [health](http://localhost:3001/health) | — | [ux](http://localhost:3001/) |
| Agent Portal | [health](http://localhost:8081/actuator/health) | — | [ux](http://localhost:8081/) |
| Agentic Log Analysis Dashboard | [health](http://localhost:4001/health) | [docs](http://localhost:4001/docs) | [ux](http://localhost:4001/) |
| PostgreSQL | `pg_isready` via Docker on TCP `localhost:5433` (not HTTP) | — | — |
| MongoDB | `mongosh` ping via Docker on TCP `localhost:27018` (not HTTP) | — | — |
| Chroma | `bash + /dev/tcp` via Docker, internal port `8000` only (not host-exposed) | — | — |

> The Shared Data API exposes Swagger as the system's integration target. The Dashboard exposes Swagger as an admin diagnostic surface. The three end-user apps (FNOL / Customer Portal / Agent Portal) are SPA + thin proxy and intentionally do not expose `/docs`. Both Swagger UIs are browser-accessible without an API key for local dev ([ADR-001](docs/decisions/ADR-001-local-docker-only.md)); to **call** endpoints from them you still need a JWT — click **Authorize** and paste a `Bearer <token>` from a login round-trip.

---

## Operating the dashboard

The dashboard ships with an Agitator (operator-driven load generator), chaos middleware
support, a Vectorstore Stats screen, and an opt-in Proactive Scan loop. Full operator
runbook is in [`docs/operations/dashboard-guide.md`](docs/operations/dashboard-guide.md).

---

## Project Resources

| Resource | What it contains |
|---|---|
| `PLAN.md` | Complete build task list — source of truth for progress |
| `CLAUDE_RESOURCES.md` | All Claude Code agents, commands, hooks, and skills |
| `.env.example` | All required environment variables |
| `docs/project-brief.md` | Narrative project overview with personas |
| `docs/development-workflow.md` | Hooks, slash commands, review flow, phase checkpoints |
| `docs/architecture/system-overview.md` | Container topology and log flow diagram |
| `docs/operations/dashboard-guide.md` | Operator runbook — Agitator, chaos, embedding cost, Vectorstore Stats, Proactive Scan |
| `docs/decisions/` | ADR-001 through ADR-016 |
| `docs/tech/tech-stack.md` | Full technology reference |
| `docs/tech/logging-strategy.md` | Per-stack logging formats and volume paths |
| `docs/tech/log-events.md` | Authoritative catalog of every structured log event emitted by the four apps |
| `docs/tech/data-model.md` | Mongo + Postgres schemas, status enum, seed counts |
| `docs/tech/file-naming-convention.md` | File and path naming rules for the repo |

---

## Common Docker Commands

| Command | Purpose |
|---|---|
| `docker compose up -d` | Build (if needed) and start all services detached, in the background |
| `docker compose ps` | List services with their status and health |
| `docker compose logs -f` | Tail live logs from all containers (or add a service name for one) |
| `docker compose build` | Rebuild images after changing a `Dockerfile` or dependencies |
| `docker compose restart <service>` | Restart a single service without touching the rest |
| `docker compose stop` | Stop all containers but **keep** containers and volumes |
| `docker compose down` | Stop and remove containers and the network — **volumes are preserved** |
| `docker compose down -v` | ⚠️ **Destructive.** Same as `down` plus deletes named volumes — wipes all DB data, accumulated logs, and the Chroma vector store. Use only for an intentional clean slate |

---

## Development Workflow

- **Branch:** always `feature/<name>` or `fix/<name>` — never commit to `main`
- **Commit:** conventional commits scoped to the app — `feat(fnol):`, `fix(customer-portal):`
- **Ship:** run `/ship` — lints, builds, commits, pushes, opens PR
- **Done:** run `/done` after merge — checks out main, pulls, deletes both local and remote branches, removes orphaned PR-time CI runs

See [`.claude/rules/workflow.md`](.claude/rules/workflow.md) for the complete pre-ship checklist.

## Contributions

🤖 This project was built in collaboration with [**Claude Code**](https://www.anthropic.com/product/claude-code).
