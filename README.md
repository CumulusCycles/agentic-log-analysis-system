# Agentic Log Analysis System

![shared-data-api](https://img.shields.io/github/actions/workflow/status/CumulusCycles/agentic-log-analysis-system/ci-shared-data-api.yml?branch=main&label=shared-data-api) ![fnol](https://img.shields.io/github/actions/workflow/status/CumulusCycles/agentic-log-analysis-system/ci-fnol.yml?branch=main&label=fnol) ![customer-portal](https://img.shields.io/github/actions/workflow/status/CumulusCycles/agentic-log-analysis-system/ci-customer-portal.yml?branch=main&label=customer-portal) ![agent-portal](https://img.shields.io/github/actions/workflow/status/CumulusCycles/agentic-log-analysis-system/ci-agent-portal.yml?branch=main&label=agent-portal) ![dashboard](https://img.shields.io/github/actions/workflow/status/CumulusCycles/agentic-log-analysis-system/ci-dashboard.yml?branch=main&label=dashboard)

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

Auth: JWT issued by Shared Data API for FNOL / Customer Portal / Agent Portal; standalone JWT for the Dashboard. See ADR-006.

---

## Build Phases

| Phase | Description | Status |
|---|---|---|
| 1 | Project scaffold — repo structure, root config, Claude Code config, docs | ✅ |
| 2 | Docker infrastructure — all 8 containers, 6 volumes, networking, healthchecks | ✅ |
| 3 | Shared Data API — sole data-access API (Mongo + Postgres), JWT auth, per-app API keys, background claim-status simulator, 7th log volume | ✅ |
| 4 | FNOL — accident report submission (FastAPI proxy to SDA) + React frontend (Vite + TypeScript + Tailwind), Playwright E2E suite | ✅ |
| 5 | Customer Portal — read-only policy/claim/profile views (Express proxy to SDA) + React frontend (Vite + TypeScript + Tailwind), Playwright E2E suite | ✅ |
| 6 | Agent Portal — claim handler tool (Spring Boot proxy to SDA) + React frontend (Vite + TypeScript + Tailwind), Playwright E2E suite | ✅ |
| 6.5 | Pre-Phase-7 best-practices pass — central error handlers, settings caching, JWT correctness fixes, ADR-010 (no security headers, local-only), SDA service-layer extraction, CP Express 4 → 5 | ✅ |
| 6.75 | Logging enrichment — success events (INFO), business-rule rejections (WARN), SDA-upstream failure logs (WARN), authoritative event catalog at `docs/tech/log-events.md`; +25 unit tests across 4 apps; "NEVER log credentials" rule codified | ✅ |
| ⛔ | **HARD STOP** — all 4 apps stable, all 4 log volumes populated | — |
| 7a | Agentic Log Analysis Dashboard — scaffold + standalone JWT auth (FastAPI + React + Tailwind), Swagger exposed, Playwright E2E suite | ✅ |
| 7b | Dashboard log ingestion — read 4 log volumes, parse native formats, `/api/logs` + `/api/status` | ✅ |
| 7c | Dashboard UI — Overview + Log Explorer screens | ⬜ |
| 7d | Dashboard semantic search — Chroma + embeddings pipeline | ⬜ |
| 7e | Dashboard LangGraph agent — AI Chat + Error Detail analysis (the LLM work) | ⬜ |

**Status:** ✅ Done · ⬜ Todo · 🔄 In Progress

> Before starting each phase, enter Plan Mode to define tasks, then update `PLAN.md`.

---

## Prerequisites

| Tool | Version | Used For |
|---|---|---|
| Docker Desktop | Latest | All containers (allocate ≥ 20 GB RAM, 8 CPUs on M1 Max) |
| `pnpm` | 9+ | Node/React apps and dashboard frontend |
| `uv` | Latest | Python apps (Shared Data API, FNOL, Agentic Log Analysis Dashboard backend) |
| Java | 21 | Agent Portal |
| Maven | 3.9+ | Agent Portal build |
| OpenAI API key | — | Phase 7 — dashboard LLM and embeddings |
| LangSmith account | — | Phase 7 — agent observability |

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

After `docker compose up -d`, click the link to verify the corresponding container is responding. Endpoints become live as their phase ships.

Each app row links the three conceptual endpoints where they apply:
**`health`** (Docker probe), **`docs`** (Swagger UI — SDA + Dashboard), **`ux`** (browser UI).

| Container | health | docs | ux | Phase |
|---|---|---|---|---|
| Shared Data API | [health](http://localhost:8002/health) | [docs](http://localhost:8002/docs) | — (API only) | 3 ✅ |
| FNOL | [health](http://localhost:8001/health) | — | [ux](http://localhost:8001/) (mobile-first) | 4 ✅ |
| Customer Portal | [health](http://localhost:3001/health) | — | [ux](http://localhost:3001/) | 5 ✅ |
| Agent Portal | [health](http://localhost:8081/actuator/health) | — | [ux](http://localhost:8081/) | 6 ✅ |
| Agentic Log Analysis Dashboard | [health](http://localhost:4001/health) | [docs](http://localhost:4001/docs) | [ux](http://localhost:4001/) | 7a ✅ |
| PostgreSQL | `pg_isready` via Docker on TCP `localhost:5433` (not HTTP) | — | — | 2 ✅ |
| MongoDB | `mongosh` ping via Docker on TCP `localhost:27018` (not HTTP) | — | — | 2 ✅ |
| Chroma | `bash + /dev/tcp` via Docker, internal port `8000` only (not host-exposed) | — | — | 2 ✅ |

> Only the Shared Data API exposes Swagger — it is the system's only integration
> target. FNOL, Customer Portal, and Agent Portal are end-user apps (SPA + thin
> proxy) and intentionally do not expose `/docs`. The SDA Swagger UI is
> browser-accessible without an API key for local dev (ADR-001); to **call**
> endpoints from it you still need a JWT — click **Authorize** and paste a
> `Bearer <token>` from a login round-trip.

> **Phase 2 note:** the DB tier (`postgres`, `mongodb`, `chroma`) is fully functional
> and reports `(healthy)`. App containers whose phase has not shipped yet run
> `tail -f /dev/null` as placeholders — they appear as `Up` without a health status.
> Phases 3–7 replace each placeholder with the real server and add its `GET /health`
> healthcheck.

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
| `docs/decisions/` | ADR-001 through ADR-007 |
| `docs/tech/tech-stack.md` | Full technology reference |
| `docs/tech/logging-strategy.md` | Per-stack logging formats and volume paths |
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
| `docker compose down -v` | Same as `down` **plus deletes named volumes** — wipes all DB data and logs |

### About `docker compose down -v`

The `-v` flag deletes the persistent volumes (`postgres-data`, `mongodb-data`, the three
`*-logs` volumes, and `chroma-data`). That means **all seeded database records, accumulated
application logs, and the Chroma vector store are permanently lost**. Use plain
`docker compose down` (without `-v`) to stop the stack while keeping that state. Only use
`-v` when you intentionally want a clean slate and have nothing in the volumes worth keeping.

---

## Development Workflow

- **Branch:** always `feature/<name>` or `fix/<name>` — never commit to `main`
- **Commit:** conventional commits scoped to the app — `feat(fnol):`, `fix(customer-portal):`
- **Ship:** run `/ship` — lints, builds, commits, pushes, opens PR
- **Done:** run `/done` after merge — checks out main, pulls, deletes both local and remote branches, removes orphaned PR-time CI runs

See `.claude/rules/workflow.md` for the complete pre-ship checklist.

## Contributions

🤖 This project was built in collaboration with [**Claude Code**](https://www.anthropic.com/product/claude-code).
