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

**Auth:** Issues JWT (HS256, `JWT_SECRET`) at `POST /auth/login`. Requires `X-API-Key` on every request **except** the public paths: `/health` (Docker healthcheck) and `/docs` / `/openapi.json` / `/redoc` (Swagger UI + OpenAPI schema — browser-accessible for local dev per ADR-001; calling endpoints from Swagger still requires JWT via the **Authorize** button). `/auth/login` and `/auth/me` require `X-API-Key`. Logs `caller=<app> user=<id> source=<value>` on every request — `source` is read from the `X-Source` header (default `prod`) per ADR-011.

**JWT claims:** `{ iss, aud, user_id, role, app, iat, exp }`. `iss` = `"shared-data-api"`, `aud` = `"agentic-log-analysis-insurance-apps"` — constants defined in `apps/shared-data-api/src/shared_data_api/auth/jwt.py`. FNOL / Customer Portal / Agent Portal **MUST** validate `iss` and `aud` when decoding (`PyJWT.decode(..., issuer=..., audience=...)`). `POST /claims` additionally enforces `jwt.app == "fnol"` as defense-in-depth against cross-app token replay.

**Schema enforcement:** Mongo unique indexes on `users.username` and `policies.policy_number`; Postgres CHECK constraints on `claims.current_status` and `claim_status_history.{from_status,to_status}` against the ADR-007 status enum. Mongo indexes are applied on startup via `ensure_indexes()`; Postgres schema is managed by Alembic (`apps/shared-data-api/alembic/`) and applied on startup via `postgres.run_migrations()` → `alembic upgrade head`. See `docs/tech/data-model.md` and ADR-008.

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

**Routes:** API surface lives under `/api/*` so the React SPA can own the top-level routes `/claims`, `/claims/:id`, `/profile`, and `/login` without conflicting with the controllers. `GET /api/health`, `POST /api/auth/login` (proxies SDA), `GET /api/profile/me` (proxies SDA `/users/{user_id}`), `GET /api/claims`, `GET /api/claims/{id}`, `GET /actuator/health` (Spring Boot Actuator — Docker healthcheck probe), `GET /` (SPA index.html).

**HTTP/1.1 only:** the Spring `RestClient` that calls SDA is pinned to `HttpClient.Version.HTTP_1_1` — uvicorn (SDA's ASGI server) does not support HTTP/2 cleartext upgrade and rejects h2c attempts with `"Unsupported upgrade request"` / 400 before the body reaches pydantic.

**Checkstyle:** project ruleset at `apps/agent-portal/checkstyle.xml` (Google Java Style — checkstyle-10.20.2 — with overrides: 4-space indentation, 120-char line length, allowedAbbreviationLength=4, no required Javadoc on types/methods). Declared in `pom.xml` with `maven-checkstyle-plugin 3.6.0` pinned to `checkstyle 10.20.2`, bound to the `verify` Maven phase — so `./mvnw -B verify` (the CI command in the `agent-portal` job of `.github/workflows/ci.yml`) enforces it on every PR.

---

## Agentic Log Analysis Dashboard (dashboard/)

**Stack:** Python 3.12 / FastAPI + React 18 + Vite + TypeScript · Chroma vector store · `uv` + `pnpm`

**Auth:** **Standalone** — local JWT signed with `DASHBOARD_JWT_SECRET`; admin credentials from `DASHBOARD_ADMIN_USERNAME` / `DASHBOARD_ADMIN_PASSWORD`. Does **not** depend on the Shared Data API to authenticate (so the dashboard stays operational when the insurance apps are sick — see ADR-006).

**Routes:** `GET /health`, `POST /api/auth/login`, `GET /api/auth/me` (all 7a ✅); `GET /api/logs`, `GET /api/status` (both 7b ✅). Phase 7c–7e routes are tracked in `.claude/rules/dashboard.md`. Swagger exposed at `/docs` (admin diagnostic tool — anonymous browser load like SDA, calling endpoints still requires JWT).

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
- **Node formatting (all Node packages):** prettier 3.x — root `.prettierrc.json` (`printWidth: 100`, `endOfLine: lf`); each package declares `prettier` in `devDependencies` + `format` (`prettier --write .`) and `format:check` (`prettier --check .`) scripts; the relevant per-app job in `.github/workflows/ci.yml` runs `pnpm format:check` after `pnpm lint`
- **Chaos middleware (SDA / FNOL / CP / AP only — dashboard is exempt):** thin header-driven failure simulator gated by `ENABLE_CHAOS` env var (default `false`). Honors `X-Chaos: slow:<ms>` (0..60000) and `X-Chaos: error:<status>` (400..599). Log level taxonomy (per ADR-013 + 2026-06-06 amendment for PR 4c): `chaos_honored` is **ERROR** when `error:<5xx>`, **WARN** when `error:<4xx>` OR `slow:<ms>`; `chaos_directive_invalid` is always **WARN**. Mounted AFTER auth (SDA: behind APIKey; AP: filter order 20 > JWT order 1) — chaos cannot bypass security. AP scopes to `/api/*` only so `/actuator/health` is never chaosed.
