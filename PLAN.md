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

## Phase 3 — Shared Data API

Backend-only FastAPI service for centralized customer and policy data.
Establishes the PostgreSQL schema used by FNOL and Agent Portal.

> **Enter Plan Mode before starting this phase.**

| Task | Status |
|---|---|
| *(tasks to be defined in Plan Mode)* | ⬜ |

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
| All 3 log volumes contain real log entries | ⬜ |
| FNOL ↔ Shared Data API integration verified end-to-end | ⬜ |
| Agent Portal reads FNOL claims correctly | ⬜ |
| All 4 app containers + 2 DBs stable together under load | ⬜ |

---

## Phase 7 — Agentic Log Analysis Dashboard

Primary deliverable. FastAPI + React + LangChain + LangGraph + OpenAI + Chroma.
Reads logs from the three log volumes read-only. Conversational AI interface.

> **Enter Plan Mode before starting this phase.**

| Task | Status |
|---|---|
| *(tasks to be defined in Plan Mode)* | ⬜ |
