# Project Rules — Per-App Stack Conventions

## App Philosophy

The four supporting apps plus the Agentic Log Analysis Dashboard are **lean but solid**.
They log normally — INFO for regular operations, WARN for recoverable issues, ERROR when
something actually fails.

Keep DB schemas simple — 3 tables/collections per app maximum.
Keep UI minimal — just enough screens to look and feel real.

---

## Shared Data API (apps/shared-data-api/)

**Stack:** Python 3.12 / FastAPI (API only, no frontend) · PostgreSQL · `uv`

**Routes:** `GET /customers/{id}`, `POST /customers`, `GET /policies/{number}`, `GET /health`

**DB Tables:** `customers`, `policies` · **Seed:** 10 customers, 15 policies

**Note:** Pure DB CRUD service — no log volume. Logs to stdout only.

---

## FNOL (apps/fnol/)

**Stack:** Python 3.12 / FastAPI + React 18 + Vite + TypeScript · PostgreSQL · `uv`

**Routes:** `POST /fnol/submit`, `GET /fnol/{claim_id}`, `GET /health`, `GET /`

**DB Tables:** `claims`, `vehicles` · **Seed:** 10 vehicles, 10 claims

---

## Customer Portal (apps/customer-portal/)

**Stack:** Node.js 20 / Express + React 18 + Vite + TypeScript · MongoDB · `pnpm`

**Routes:** `GET /policies/:userId`, `GET /claims/:userId`, `PUT /profile/:userId`, `GET /health`, `GET /`

**DB Collections:** `users`, `policies`, `claims` · **Seed:** 5 users, 10 policies, 10 claims

---

## Agent Portal (apps/agent-portal/)

**Stack:** Java 21 / Spring Boot 3 + React 18 + Vite + TypeScript · PostgreSQL · Maven

**Routes:** `GET /claims`, `PUT /claims/{id}/assign`, `PUT /claims/{id}/status`, `GET /actuator/health`, `GET /`

**DB Tables:** `adjusters`, `assignments` (reads FNOL's `claims` table — same PostgreSQL instance) · **Seed:** 5 adjusters, 5 assignments

---

## Agentic Log Analysis Dashboard (dashboard/)

**Stack:** Python 3.12 / FastAPI + React 18 + Vite + TypeScript · Chroma vector store · `uv` + `pnpm`

**Routes:** Placeholder routes defined in `.claude/rules/dashboard.md`; full API surface implemented in Phase 7.

**Data:** Chroma persistent collection of log embeddings — no relational tables, no seed.

**Note:** Primary deliverable. Reads from `fnol-logs`, `customer-portal-logs`, and `agent-portal-logs` volumes read-only. Full conventions in `.claude/rules/dashboard.md`.

---

## General Conventions (All Apps)

- Single container per app — apps with a UI serve both API and React frontend; Shared Data API is API-only
- Each app exposes `/health` (Agent Portal: `/actuator/health`)
- Shared Data API logs to stdout only; FNOL, Customer Portal, and Agent Portal write logs to `/app/logs/` (mapped to persistent volume); Agentic Log Analysis Dashboard logs to stdout and reads the three app log volumes read-only
- Environment variables via `.env` — never hardcoded
- Seed data will load on startup if the DB is empty — idempotent
- **TypeScript module naming (all React apps):** `kebab-case.ts` for non-component modules and utilities; React components use `PascalCase.tsx`
