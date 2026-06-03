# Agentic Log Analysis System — Build Plan

This file is the single source of truth for the entire project build sequence.
Managed by Claude Code. Update task status before every `/ship`.

**Before starting any phase:** enter Plan Mode to define detailed tasks for that phase,
then update this file with those tasks before implementation begins.

**Status legend:** ⬜ Todo · 🔄 In Progress · ✅ Done

---

## Phase 1 — Project Scaffold

Stand up the repo skeleton: root config files (`CLAUDE.md`, `CLAUDE_RESOURCES.md`, `PLAN.md`,
`.env.example`, `.gitignore`, `.gitattributes`, `.mcp.json`, `LICENSE`, `README.md`),
Claude Code config (`.claude/` — rules, agents, commands, hooks, skills, settings),
and `docs/` (architecture, tech, decisions).

| Task | Status |
|---|---|
| Verify all Claude Code config files in place | ✅ |
| Verify all docs in place | ✅ |
| Add `.gitattributes` covering every project stack, lock-file diff suppression, binary markers, and Claude Code hook LF enforcement | ✅ |

---

## Phase 2 — Docker Infrastructure

Define the full `docker-compose.yml`: all 8 containers, 6 persistent volumes,
`insurance-net` bridge network, healthchecks, ARM64 platform flags.

DB tier (postgres, mongodb, chroma) ships fully functional with real healthchecks.
App tier (shared-data-api, fnol-app, customer-portal, agent-portal, log-dashboard)
ships as bare-bones placeholders running `tail -f /dev/null` — Phases 3–7 replace
each with the real server, adding the port mapping, healthcheck, and
`condition: service_healthy` on depends_on.

| Task | Status |
|---|---|
| Create `feature/phase-2-docker-infrastructure` branch | ✅ |
| Write root `docker-compose.yml` (8 services, 6 volumes, `insurance-net`, ARM64) | ✅ |
| Configure `postgres` with healthcheck and persistent volume | ✅ |
| Configure `mongodb` with healthcheck and persistent volume | ✅ |
| Configure `chroma` 1.5.9 with healthcheck (internal port only) | ✅ |
| Add placeholder app services with base runtime images + `tail -f /dev/null` (no ports, no healthcheck) | ✅ |
| Wire log volumes (FNOL/CP/AP write, log-dashboard read-only) | ✅ |
| Wire `depends_on` (log-dashboard waits for `chroma` `service_healthy`) | ✅ |
| Fix `chroma` heartbeat path drift (`/api/v1/` → `/api/v2/`) in `infrastructure.md` | ✅ |
| `docker compose config` passes | ✅ |
| `docker compose up -d` brings DB tier healthy; app tier placeholders stay `Up` | ✅ |
| Update README phase table and remove Quick Start caveat | ✅ |
| Update `docs/architecture/system-overview.md` depends_on note | ✅ |
| Run `/ship`: self-review → security-review → verify → push → PR | ✅ |

---

## Pre-Phase-3 — Architecture Pivot (Docs & Rules Only)

Captures the data-layer, auth, and simulator decisions in docs, rules, and ADRs so
Phase 3 implementation can land cleanly. No code or container changes in this PR.

| Task | Status |
|---|---|
| Add ADR-005 (Shared Data API as sole data layer), ADR-006 (auth strategy), ADR-007 (claim-status simulator) | ✅ |
| Mark ADR-004 superseded by ADR-005 (and ADR-003 amended) | ✅ |
| Add `docs/tech/data-model.md` (Mongo + Postgres schemas, status enum, seed counts) | ✅ |
| Update `docs/project-brief.md`, `docs/architecture/system-overview.md`, `docs/tech/{tech-stack,logging-strategy}.md`, `docs/README.md` | ✅ |
| Update `.claude/rules/*` (project, apps, dashboard, logging, infrastructure) | ✅ |
| Update `README.md` architecture + resources tables | ✅ |
| Rewrite `.env.example` (remove direct DB envs for FNOL/CP/AP; add JWT, API keys, admin creds, demo logins) | ✅ |
| Run `/ship`: pre-ship doc check → self-review → security-review → commit → push → PR | ✅ |

---

## Phase 3 — Shared Data API

Backend FastAPI service. Sole data-access layer (Mongo for users/policies, Postgres for
claims). Issues JWTs for FNOL/CP/AP, enforces per-app API keys, runs background
claim-status simulator, writes logs to 7th volume `shared-data-api-logs`.
Full scope in `.claude/rules/apps.md` and `docs/tech/data-model.md`.

| Task | Status |
|---|---|
| Create `feature/phase-3-shared-data-api` branch | ✅ |
| Scaffold `apps/shared-data-api/` uv project (`pyproject.toml`, `.python-version`, `.dockerignore`) | ✅ |
| Write `Dockerfile` (multi-stage uv build, ARM64, non-root, runs `uvicorn`) | ✅ |
| Add `config.py` (pydantic-settings: JWT, API keys, DB URLs, simulator tick) | ✅ |
| Add `logging_setup.py` (structlog JSON to stdout + `/app/logs/shared-data-api.log`) | ✅ |
| Add Postgres async engine + SQLAlchemy models (`claims`, `claim_status_history`) | ✅ |
| Add Mongo Motor client + `get_db()` | ✅ |
| Add JWT (PyJWT HS256) + bcrypt password utilities | ✅ |
| Add `APIKeyMiddleware` (validates `X-API-Key`, resolves `caller`) | ✅ |
| Add `RequestLoggerMiddleware` (`caller`, `user`, `method`, `path`, `status`, `duration_ms`) | ✅ |
| Add routers: health, auth, users, policies, claims (with FNOL-only `POST /claims`) | ✅ |
| Add idempotent seed routine (10 customers, 5 agents, 15 policies, ~10 claims) | ✅ |
| Add background claim-status simulator (asyncio lifespan task, ADR-007) | ✅ |
| Wire FastAPI app + lifespan (init → seed → simulator → yield → teardown) | ✅ |
| Add pytest suite (health, auth, api_key, claims read/write, policies, simulator) | ✅ |
| Swap `shared-data-api` placeholder in `docker-compose.yml` (build, port 8002:8000, healthcheck, volume, depends_on conditions) | ✅ |
| Upgrade FNOL / CP / AP `depends_on` to `shared-data-api: service_healthy` | ✅ |
| Add `shared-data-api-logs` to top-level `volumes:` block | ✅ |
| `docker compose config --quiet` passes; `docker compose up -d shared-data-api` reaches `healthy` | ✅ |
| Verify `/app/logs/shared-data-api.log` contains structured JSON lines | ✅ |
| End-to-end: login → token → `/auth/me` with `X-API-Key` works | ✅ |
| Multi-pass review and fix — Critical (5), Medium (10), Low (5), Functional (3); 85 tests total | ✅ |
| ADR-008 (defer Alembic to post-Phase-3 PR) | ✅ |
| Documentation drift fixes — `.claude/rules/apps.md`, `docs/tech/data-model.md`, `docs/tech/logging-strategy.md`, `docs/README.md`, `README.md` | ✅ |
| Run `/ship`: pre-ship doc check → self-review → security-review → lint → build → test → commit → push → PR | ✅ |

---

## Alembic Baseline — Schema Management for Phase 4+

Lands Alembic ahead of Phase 4 per ADR-008, before FNOL begins writing persistent
claims that schema changes must preserve. Generates the baseline migration from the
Phase 3 models, swaps the lifespan from `create_all()` to `run_migrations()`, and
replaces the "wipe `postgres-data` to evolve schema" runbook with the `alembic revision`
workflow. Tests continue to use SQLite + `create_all()` directly via an autouse
conftest bypass.

| Task | Status |
|---|---|
| Create `feature/alembic-baseline` branch | ✅ |
| Add `alembic` dep to `pyproject.toml` + regenerate `uv.lock` | ✅ |
| Scaffold `apps/shared-data-api/alembic/` (env.py async pattern, blank `sqlalchemy.url`) | ✅ |
| Generate baseline migration via `alembic revision --autogenerate -m "phase 3 baseline"` | ✅ |
| Hand-verify migration: both tables, CHECK constraints, JSONB/BigInteger variants, FK, PK | ✅ |
| Add `postgres.run_migrations()` (5-retry/2s-backoff, `asyncio.to_thread`) | ✅ |
| Swap `main.py` lifespan: `postgres.create_all()` → `postgres.run_migrations()` | ✅ |
| Update `Dockerfile` to copy `alembic/` and `alembic.ini` | ✅ |
| Add `_bypass_run_migrations` autouse fixture in `tests/conftest.py` (with opt-out marker) | ✅ |
| Replace `test_create_all_retry.py` with `test_run_migrations.py` (3 retry tests against mocked `command.upgrade`) | ✅ |
| Exclude `alembic/versions/` from ruff/black (autogen output has unavoidable long SQL strings) | ✅ |
| `uv run pytest -v` passes (91 tests) | ✅ |
| Container build + healthy startup; `alembic_version` table populated; structured JSON logs preserved end-to-end | ✅ |
| Auth round-trip works against Alembic-managed schema | ✅ |
| Downgrade smoke test: `alembic downgrade base` then `upgrade head` cycle clean | ✅ |
| Update `docs/tech/data-model.md` "Schema evolution" section with Alembic workflow | ✅ |
| Update `.claude/rules/apps.md` schema-enforcement line | ✅ |
| Run `/ship`: pre-ship doc check → self-review → security-review → lint → build → test → commit → push → PR | ✅ |

---

## Phase 4 — FNOL

Mobile-first accident reporting app. FastAPI backend + React frontend.
Depends on Shared Data API for customer/policy validation.

> **Enter Plan Mode before starting this phase.**

| Task | Status |
|---|---|
| *(tasks to be defined in Plan Mode)* | ⬜ |

---

## Phase 5 — Customer Portal

Policyholder self-service app. Express backend + React frontend + MongoDB.

> **Enter Plan Mode before starting this phase.**

| Task | Status |
|---|---|
| *(tasks to be defined in Plan Mode)* | ⬜ |

---

## Phase 6 — Agent Portal

Internal claim handler app. Spring Boot backend + React frontend + PostgreSQL.

> **Enter Plan Mode before starting this phase.**

| Task | Status |
|---|---|
| *(tasks to be defined in Plan Mode)* | ⬜ |

---

## ⛔ HARD STOP — Pre-Dashboard Checklist

**Do not start Phase 7 until every item below is confirmed.**

| Checkpoint | Status |
|---|---|
| All 4 app containers start healthy (`docker compose up`) | ⬜ |
| All 4 apps pass their full test suites | ⬜ |
| All 4 log volumes contain real log entries | ⬜ |
| FNOL ↔ Shared Data API integration verified end-to-end | ⬜ |
| Agent Portal reads claims via Shared Data API correctly | ⬜ |
| Shared Data API auth (JWT + API key) round-trips for FNOL/CP/AP | ⬜ |
| All 4 app containers + 2 DBs stable together under load | ⬜ |

---

## Phase 7 — Agentic Log Analysis Dashboard

Primary deliverable. FastAPI + React + LangChain + LangGraph + OpenAI + Chroma.
Reads logs from the three log volumes read-only. Conversational AI interface.

> **Enter Plan Mode before starting this phase.**

| Task | Status |
|---|---|
| *(tasks to be defined in Plan Mode)* | ⬜ |
