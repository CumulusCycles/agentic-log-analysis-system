# Agentic Log Analysis System

An AI-powered log management platform built on a realistic insurance application ecosystem.
Four full-stack apps generate heterogeneous logs in their native formats; a LangGraph + OpenAI
dashboard continuously monitors, correlates, and explains them.

The supporting apps are the raw material. **The dashboard is the product.**

---

## Architecture

| App | Stack | Purpose |
|---|---|---|
| **Shared Data API** | Python / FastAPI | Centralized customer and policy data (no UI) |
| **FNOL** | Python / FastAPI + React | First Notice of Loss — accident reporting (mobile) |
| **Customer Portal** | Node / Express + React | Policyholder self-service (desktop) |
| **Agent Portal** | Java / Spring Boot + React | Internal claim handler tool (desktop) |
| **Agentic Log Analysis Dashboard** | Python / FastAPI + React + LangGraph | Agentic log analysis — the primary deliverable |

Infrastructure: PostgreSQL · MongoDB · Chroma vector store · Docker Compose · `insurance-net` bridge network

---

## Build Phases

| Phase | Description | Status |
|---|---|---|
| 1 | Project scaffold — repo structure, root config, Claude Code config, docs | ✅ |
| 2 | Docker infrastructure — all 8 containers, 6 volumes, networking, healthchecks | ⬜ |
| 3 | Shared Data API — PostgreSQL schema, customer/policy endpoints | ⬜ |
| 4 | FNOL — accident report submission + React frontend | ⬜ |
| 5 | Customer Portal — policy/claim views + React frontend + MongoDB | ⬜ |
| 6 | Agent Portal — claim handler tool + React frontend | ⬜ |
| ⛔ | **HARD STOP** — all 4 apps stable, all 3 log volumes populated | — |
| 7 | Agentic Log Analysis Dashboard — LangChain + LangGraph + OpenAI + Chroma + React UI | ⬜ |

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

> Available once **Phase 2** adds `docker-compose.yml`. Until then, see `PLAN.md` for build status.

```bash
# 1. Copy the environment template and fill in your values
cp .env.example .env

# 2. Build and start all services in the background
docker compose up -d

# 3. Verify every container is running and healthy
docker compose ps
```

### Common Docker Commands

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

## Project Resources

| Resource | What it contains |
|---|---|
| `PLAN.md` | Complete build task list — source of truth for progress |
| `CLAUDE_RESOURCES.md` | All Claude Code agents, commands, hooks, and skills |
| `.env.example` | All required environment variables |
| `docs/project-brief.md` | Narrative project overview with personas |
| `docs/development-workflow.md` | Hooks, slash commands, review flow, phase checkpoints |
| `docs/architecture/system-overview.md` | Container topology and log flow diagram |
| `docs/decisions/` | ADR-001 through ADR-004 |
| `docs/tech/tech-stack.md` | Full technology reference |
| `docs/tech/logging-strategy.md` | Per-stack logging formats and volume paths |
| `docs/tech/file-naming-convention.md` | File and path naming rules for the repo |

---

## Development Workflow

- **Branch:** always `feature/<name>` or `fix/<name>` — never commit to `main`
- **Commit:** conventional commits scoped to the app — `feat(fnol):`, `fix(customer-portal):`
- **Ship:** run `/ship` — lints, builds, commits, pushes, opens PR
- **Done:** run `/done` after merge — checks out main, pulls, deletes both local and remote branches

See `.claude/rules/workflow.md` for the complete pre-ship checklist.

## Contributions

🤖 This project was built in collaboration with [**Claude Code**](https://www.anthropic.com/product/claude-code).
