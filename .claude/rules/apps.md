# Project Rules — Per-App Stack Conventions

## App Philosophy

The four supporting apps plus the Agentic Log Analysis Dashboard are **lean but solid**.
They log normally — INFO for regular operations, WARN for recoverable issues, ERROR when
something actually fails.

Keep DB schemas simple — 3 tables/collections per app maximum.
Keep UI minimal — just enough screens to look and feel real.

---

## Shared Data API (apps/shared-data-api/)

**Stack:** Python 3.12 / FastAPI (API only, no frontend) · PostgreSQL + MongoDB · `uv`

**Role:** Sole data-access layer for the system. Owns both databases (see ADR-005 and `docs/tech/data-model.md`).

**Routes:**
- `POST /auth/login`, `GET /auth/me`
- `GET /users/{id}`
- `GET /policies/{number}`, `GET /policies?customer_id=...`
- `GET /claims?...`, `GET /claims/{id}`
- `POST /claims` — FNOL only (enforced by `X-API-Key`)
- `GET /health`

**Data ownership:** `users`, `policies` (with embedded vehicles) in Mongo; `claims`, `claim_status_history` in Postgres. Full schemas in `docs/tech/data-model.md`.

**Auth:** Issues JWT (HS256, `JWT_SECRET`) at `POST /auth/login`. Requires `X-API-Key` on every non-`/auth/login` non-`/health` request; logs `caller=<app> user=<id>` on every request.

**Background task:** In-process asyncio claim-status simulator advances claim statuses on a tick — see ADR-007.

**Seed:** 10 customers, 5 agents, 15 policies (with embedded vehicles), ~10 claims in mixed statuses.

**Logs:** Writes to `/app/logs/shared-data-api.log` → volume: `shared-data-api-logs`. Also to stdout.

---

## FNOL (apps/fnol/)

**Stack:** Python 3.12 / FastAPI + React 18 + Vite + TypeScript · `uv`

**Data:** Via Shared Data API (HTTP). No direct DB driver. Sole write path for `POST /claims`.

**Auth:** JWT via Shared Data API `POST /auth/login`. Inter-service header: `X-API-Key: $SHARED_DATA_API_KEY_FNOL`.

**Routes:** `POST /fnol/submit` (calls SDA `POST /claims`), `GET /fnol/{claim_id}` (calls SDA `GET /claims/{id}`), `POST /auth/login` (proxies SDA), `GET /health`, `GET /`

---

## Customer Portal (apps/customer-portal/)

**Stack:** Node.js 20 / Express + React 18 + Vite + TypeScript · `pnpm`

**Data:** Via Shared Data API (HTTP, **read-only**). No direct DB driver, no Mongoose.

**Auth:** JWT via Shared Data API `POST /auth/login`. Inter-service header: `X-API-Key: $SHARED_DATA_API_KEY_CUSTOMER_PORTAL`.

**Routes:** `GET /policies/me`, `GET /claims/me`, `GET /profile/me`, `POST /auth/login` (proxies SDA), `GET /health`, `GET /`

---

## Agent Portal (apps/agent-portal/)

**Stack:** Java 21 / Spring Boot 3 + React 18 + Vite + TypeScript · Maven

**Data:** Via Shared Data API (HTTP, **read-only**). No direct DB driver, no Spring Data JPA. Status transitions are driven by the SDA simulator (ADR-007), not by agents.

**Auth:** JWT via Shared Data API `POST /auth/login`. Inter-service header: `X-API-Key: $SHARED_DATA_API_KEY_AGENT_PORTAL`.

**Routes:** `GET /claims`, `GET /claims/{id}`, `POST /auth/login` (proxies SDA), `GET /actuator/health`, `GET /`

---

## Agentic Log Analysis Dashboard (dashboard/)

**Stack:** Python 3.12 / FastAPI + React 18 + Vite + TypeScript · Chroma vector store · `uv` + `pnpm`

**Auth:** **Standalone** — local JWT signed with `DASHBOARD_JWT_SECRET`; admin credentials from `DASHBOARD_ADMIN_USERNAME` / `DASHBOARD_ADMIN_PASSWORD`. Does **not** depend on the Shared Data API to authenticate (so the dashboard stays operational when the insurance apps are sick — see ADR-006).

**Routes:** `POST /api/auth/login`, `GET /api/auth/me`, plus the Phase 7 routes in `.claude/rules/dashboard.md`.

**Data:** Chroma persistent collection of log embeddings — no relational tables, no seed.

**Note:** Primary deliverable. Reads from `shared-data-api-logs`, `fnol-logs`, `customer-portal-logs`, and `agent-portal-logs` volumes read-only (4 mounts). Full conventions in `.claude/rules/dashboard.md`.

---

## General Conventions (All Apps)

- Single container per app — apps with a UI serve both API and React frontend; Shared Data API is API-only
- Each app exposes `/health` (Agent Portal: `/actuator/health`)
- All four log-volume writers (Shared Data API, FNOL, Customer Portal, Agent Portal) write logs to `/app/logs/` mapped to their own persistent volume. The Agentic Log Analysis Dashboard logs to stdout and reads all four log volumes read-only.
- All four apps require login (no registration). Pre-seeded credentials documented in `.env.example`.
- Environment variables via `.env` — never hardcoded
- Seed data will load on startup if the DB is empty — idempotent (Shared Data API only — the other apps have no DB)
- **TypeScript module naming (all React apps):** `kebab-case.ts` for non-component modules and utilities; React components use `PascalCase.tsx`
