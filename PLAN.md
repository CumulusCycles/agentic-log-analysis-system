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

Mobile-first accident reporting app. FastAPI backend (claim submission proxy + JWT
validation + login proxy) + React 18 + Vite + TypeScript + Tailwind frontend.
No database — talks to the Shared Data API over HTTP. Sole write path for `POST /claims`
in the system (SDA enforces via `caller=fnol` + `jwt.app=fnol`).

| Task | Status |
|---|---|
| Create `feature/phase-4-fnol` branch | ✅ |
| Scaffold `apps/fnol/` uv project (`pyproject.toml`, `.python-version`, `.dockerignore`) | ✅ |
| Add backend modules — `config.py`, `logging_setup.py`, `auth/jwt.py` (decode-only), `middleware/request_logger.py`, `schemas.py` | ✅ |
| Add `clients/shared_data_api.py` — async `httpx.AsyncClient` wrapper with `X-API-Key` on every call | ✅ |
| Add routers — `health.py`, `auth.py` (proxies SDA), `claims.py` (verify JWT → call SDA) | ✅ |
| Add `main.py` — FastAPI + lifespan + middleware + SPA-fallback static mount | ✅ |
| Add backend pytest suite (20 tests: health, jwt validation, auth login, submit claim, get claim — SDA mocked via respx) | ✅ |
| Backend lint + tests pass | ✅ |
| Scaffold React frontend — pnpm, Vite 6, TypeScript, Tailwind 3, ESLint 9, Vitest 3 | ✅ |
| Add frontend source — `types/api.ts`, `lib/{api,auth,auth-context}`, `components/RequireAuth.tsx`, three pages, `App.tsx` | ✅ |
| Add Vitest unit tests (7 tests across 3 page components) + Node 25 localStorage polyfill | ✅ |
| Frontend typecheck + ESLint + Vitest + production build (~174 kB) all pass | ✅ |
| Multi-stage `Dockerfile` — `node:22-alpine` (React build) + `python:3.12-slim` (uv deps + runtime, non-root) | ✅ |
| Swap `fnol-app` block in `docker-compose.yml` — build, port 8001:8000, healthcheck, drop `postgres` dep | ✅ |
| Add `SHARED_DATA_API_BASE_URL=http://shared-data-api:8000` to `.env.example` | ✅ |
| Cold-start verification — `docker compose down` + volume wipe of all 7 named volumes + `up -d`; all 8 containers come back healthy | ✅ |
| Host-side functional probes — `/health`, `/auth/login`, `/fnol/submit`, `/fnol/{id}`; verify `caller=fnol` in SDA logs; `fnol-logs` volume populated | ✅ |
| **Playwright E2E suite — 5 specs × 2 viewports (desktop-chromium + mobile-safari); 33 passing, 3 skipped (intentional mobile-only)** | ✅ |
| Bug fix during E2E: FastAPI SPA fallback for unknown client-side routes (caught by `navigation.spec.ts`) | ✅ |
| Extend `/ship` skill to run every app's test suite (backend + frontend unit + Playwright E2E) | ✅ |
| Run `/ship`: pre-ship doc check → reviews → lint → build → all-apps tests → commit → push → PR | ✅ |

---

## Phase 5 — Customer Portal

Policyholder self-service app. Node 20 / Express + TypeScript backend (read-only
proxy to SDA — no DB) + React 18 + Vite + TypeScript + Tailwind frontend. Browses
the customer's policies, claims, and profile. JWT issued by SDA's `/auth/login`;
every outbound SDA call carries `X-API-Key: $SHARED_DATA_API_KEY_CUSTOMER_PORTAL`
per ADR-006.

| Task | Status |
|---|---|
| Create `feature/phase-5-customer-portal` branch | ✅ |
| Scaffold `apps/customer-portal/` pnpm project (`package.json`, `tsconfig.json`, `.dockerignore`) | ✅ |
| Backend modules — `config.ts` (zod-validated env), `logger.ts` (winston JSON), `errors.ts`, `spa.ts` (path-traversal-safe SPA fallback) | ✅ |
| Backend middleware — `request-logger.ts` (caller/user/method/path/status/duration_ms), `require-auth.ts` (jsonwebtoken decode w/ iss+aud verification) | ✅ |
| Backend `clients/sda-client.ts` — axios wrapper with `X-API-Key` on every call | ✅ |
| Backend routers — `health.ts`, `auth.ts` (login proxy), `profile.ts`, `policies.ts`, `claims.ts` (each protected, mounted at exact path so SPA fallback can claim `/policies`, `/claims`, `/profile`) | ✅ |
| Backend Vitest suite (25 tests: health, auth-login, profile, policies, claims, require-auth, spa-fallback — SDA mocked via nock) | ✅ |
| Backend typecheck + ESLint + tsc build pass | ✅ |
| Scaffold React frontend — pnpm, Vite 6, TypeScript 5, Tailwind 3, ESLint 9, Vitest 3, Playwright 1.60 (copied verbatim from FNOL) | ✅ |
| Frontend source — `types/api.ts` (UserOut, PolicyOut, ClaimOut), `lib/{api,auth,auth-context}`, `components/{RequireAuth,TopNav,StatusBadge}`, four pages (Login, Policies, Claims, Profile), `App.tsx` | ✅ |
| Frontend Vitest unit tests (8 tests across 4 page components) + Node 25 localStorage polyfill | ✅ |
| Frontend typecheck + ESLint + Vitest + production build pass | ✅ |
| Multi-stage `Dockerfile` — `node:22-alpine` (frontend build + backend tsc) + `node:20-alpine` runtime (non-root `node:1000`) | ✅ |
| Swap `customer-portal` block in `docker-compose.yml` — build, port 3001:3000, healthcheck, drop `mongodb` dep | ✅ |
| `.env.example` already has `SHARED_DATA_API_KEY_CUSTOMER_PORTAL` from architecture pivot — no change | ✅ |
| Cold-start verification — `docker compose down` + volume wipe of all 7 named volumes + `up -d`; all 8 containers come back healthy from zero | ✅ |
| Host-side functional probes — `/health`, `/auth/login`, `/profile/me`, `/policies/me`, `/claims/me`; verify `caller=customer-portal` in SDA logs; `customer-portal-logs` volume populated | ✅ |
| **Playwright E2E suite — 5 specs × 2 viewports (desktop-chromium + mobile-safari); 28 passing** | ✅ |
| Bug fix during E2E: mount each protected endpoint at exact path so `/policies`, `/claims`, `/profile` fall through to the SPA fallback (not 401 from `requireAuth`) | ✅ |
| Unlock SDA `/docs` + `/openapi.json` + `/redoc` for browser access (ADR-001 local-only threat model — JWT still required to invoke endpoints from Swagger) | ✅ |
| Consolidate README healthcheck table — each app on one line with multiple links | ✅ |
| Run `/ship`: pre-ship doc check → reviews → lint → build → all-apps tests → commit → push → PR | ✅ |

---

## Phase 6 — Agent Portal

Internal claim handler app. Java 21 / Spring Boot 3 backend + React 18 / Vite / TypeScript / Tailwind frontend, served as one container. Reads claims via the Shared Data API.

| Task | Status |
|---|---|
| Maven scaffold (`pom.xml`, Maven Wrapper `mvnw` + `.mvn/wrapper/`, `groupId=com.cumuluscycles`, `artifactId=agent-portal`) | ✅ |
| Backend source — `AgentPortalApplication`, `AppProperties` (zod-equivalent via `@ConfigurationProperties + @Validated`), `SdaClient` (Spring `RestClient` pinned to HTTP/1.1 — uvicorn rejects h2c upgrade), `JwtAuthenticationFilter` (`OncePerRequestFilter` — verifies HS256 / `iss` / `aud`), `RequestLoggingFilter`, SPA static + path-traversal-safe resolver | ✅ |
| API surface mounted under `/api/*` (deviation from CP) — `/api/health`, `/api/auth/login`, `/api/profile/me`, `/api/claims`, `/api/claims/{id}` — leaves React Router free for `/claims`, `/claims/:id`, `/profile`, `/login` | ✅ |
| Logback `logback-spring.xml` — Console + RollingFileAppender to `/app/logs/agent-portal.log`, pattern matches `.claude/rules/logging.md` | ✅ |
| Backend tests — JUnit 5 + Spring Boot Test + Mockito @MockitoBean SdaClient — 24 tests (Auth/Profile/Claims controllers, JwtAuthenticationFilter for iss/aud/expired/wrong-secret/missing-header, SpaFallback for `/`, SPA routes, `/api/missing`, path-traversal) | ✅ |
| Frontend scaffold copied verbatim from Customer Portal — package.json, pnpm-workspace.yaml (`allowBuilds: esbuild: true`), tsconfig, vite/vitest/playwright/tailwind/postcss/eslint configs, MemoryStorage polyfill — customized to `VITE_AGENT_PORTAL_API_BASE_URL` + `http://localhost:8081` | ✅ |
| Frontend source — pages (Login → `/claims`, Claims list, **Claim detail + StatusTimeline**, Profile), components (RequireAuth, TopNav, StatusBadge, StatusTimeline), lib (`api.ts` hits `/api/*`, `auth.ts` with `STORAGE_KEY="agent_portal_token"`), types | ✅ |
| Frontend unit tests — Vitest 3 + jsdom + @testing-library/react — 8 tests | ✅ |
| Playwright E2E — 5 specs × 2 viewports = **30 tests pass** against live stack | ✅ |
| Multi-stage `Dockerfile` — `node:22-alpine` (frontend build) → `maven:3.9-eclipse-temurin-21-alpine` (backend build) → `eclipse-temurin:21-jre-alpine` (runtime, non-root `app:1000`) | ✅ |
| Swap `agent-portal` block in `docker-compose.yml` — build, port 8081:8080, actuator healthcheck (`wget /actuator/health \| grep UP`), drop `postgres` dep | ✅ |
| `.env.example` already has `SHARED_DATA_API_KEY_AGENT_PORTAL` + `VITE_AGENT_PORTAL_API_BASE_URL` from architecture pivot — no change | ✅ |
| Cold-start verification — full stack (all 8 containers) healthy with new AP image | ✅ |
| Host-side functional probes — `/actuator/health`, `/api/health`, `/api/auth/login` (`agent1`/`agent`), `/api/profile/me`, `/api/claims` (count=16), `/api/claims/{id}` (status history present); verify `caller=agent-portal` in SDA logs; `agent-portal-logs` volume populated with Logback lines | ✅ |
| HTTP/2 trap fix — JDK `HttpClient` defaults to HTTP/2 cleartext upgrade; uvicorn rejects with "Unsupported upgrade request" → pin `HttpClient.Version.HTTP_1_1` in `SdaClientConfig` | ✅ |
| Update `.claude/rules/apps.md` AP routes to `/api/*` prefix + add `GET /api/profile/me` | ✅ |
| Run `/ship`: pre-ship doc check → reviews → lint → build → all-apps tests → commit → push → PR | ✅ |

---

## Phase 6.5 — Pre-Phase-7 Best-Practices Pass

Hygiene pass across all four supporting apps before Phase 7. Three concern-grouped PRs:
PR 1 — central error handlers, settings cache, JWT correctness fixes, ADR-010, auth-test
depth where missing. PR 2 — extract SDA `create_claim` into a service layer.
PR 3 — upgrade CP from Express 4 to 5, collapse per-route try/catch.

| Task | Status |
|---|---|
| PR 1 — SDA: `@lru_cache` on `get_settings()`, NEW `exception_handlers.py` (3 handlers: HTTPException / RequestValidationError / Exception), wired in `main.py`, removed redundant scheme re-check in `get_current_user`, +wrong-signature + malformed-token JWT tests, +3 exception-handler tests | ✅ |
| PR 1 — FNOL backend: `@lru_cache` on `get_settings()`, NEW `exception_handlers.py` (3 handlers + `httpx.RequestError` → 502 classification), `auth/jwt.py` now uses `HTTPBearer` and stashes `bearer` on `request.state`, removed `_bearer_from` helper, +4 exception-handler tests | ✅ |
| PR 1 — FNOL frontend: `base64urlDecode` helper re-pads to mod 4 before `atob`, `decodeJwt` also rejects non-3-segment tokens, +3 `auth.test.tsx` tests with a precondition-asserted padding regression | ✅ |
| PR 1 — CP backend: NEW `error-handler.ts` (`AppError` → status passthrough / `SyntaxError` → 400 / default → generic 500 with winston ERROR log), mounted as last middleware in `buildApp()`, +3 supertest tests | ✅ |
| PR 1 — AP backend: `GlobalExceptionHandler` gains `@ExceptionHandler(Exception.class)` catch-all + `HttpMessageNotReadableException` handler, `JwtAuthenticationFilter` uses Jackson `ObjectMapper` for JSON body (replaces raw string concat), `WebConfig` wires the new constructor arg, +malformed-token test on `JwtAuthenticationFilterTest`, NEW `GlobalExceptionHandlerTest` (RuntimeException → 500 + malformed JSON → 400) | ✅ |
| PR 1 — Docs: ADR-010 codifies "no security headers in local-only deployment"; CLAUDE.md Security bullet cross-refs ADR-010; PLAN/README add Phase 6.5 row | ✅ |
| PR 1 — Run `/ship`: pre-ship doc check → reviews → lint → build → all-apps unit tests → live-stack functional probes → E2E sweep → commit → push → PR | ✅ |
| PR 2 — Extract SDA `create_claim` into a service-layer module; controller shrinks to ~12 lines; +13 service-layer unit tests | ✅ |
| PR 3 — CP Express 4 → 5 upgrade; collapse per-route `try/catch` wrappers; tighten `sda-client.ts` return types from `Promise<unknown>` to typed DTOs | ✅ |

---

## Phase 6.75 — Logging Enrichment (Pre-Dashboard Signal Boost)

Enriches every app with success events at INFO, degraded paths at WARN, and a
binding "NEVER log credentials" discipline (codified in PR #22). Single PR
across all 4 apps. New event catalog at `docs/tech/log-events.md` is the
authoritative inventory the dashboard agent will consume.

| Task | Status |
|---|---|
| SDA: +`login_success` / `login_failed` (auth router); +`claim_created` / `claim_validation_rejected` (9 rule sites) (claims_service); +`policy_fetched` / `claim_fetched` / `user_fetched` (read routers); +9 unit tests | ✅ |
| FNOL: +`login_proxied_success` (auth router); +`claim_submitted` (claims router); +`sda_upstream_rejected` / `sda_upstream_unreachable` (SDA client, 3 methods); +4 unit tests | ✅ |
| CP: +`login_proxied_success` / `policies_fetched` / `claims_fetched` / `profile_fetched` (routers); +`sda_upstream_rejected` / `sda_upstream_unreachable` (sda-client); rename `unhandled_error` → `unhandled_exception` (cross-app parser consistency); +6 unit tests | ✅ |
| AP: +`login_proxied_success` (AuthController); +`claims_fetched` / `claim_fetched` (ClaimsController); +`profile_fetched` (ProfileController); +`sda_upstream_rejected` / `sda_upstream_unreachable` (SdaClient); +6 unit tests | ✅ |
| Docs: NEW `docs/tech/log-events.md` (authoritative event catalog: 24 SDA + 12 FNOL + 12 CP + 9 AP events with level/fields/trigger); cross-link from `logging-strategy.md` | ✅ |
| Credential audit: zero hits across all 4 apps; live-stack probe confirms NO bearer / NO password / NO API key in any log volume | ✅ |
| Run `/ship`: pre-ship doc check → reviews → lint → build → all-apps unit tests (118 SDA + 30 FNOL + 34 CP + 33 AP) → live-stack functional probes → E2E sweep (33 FNOL + 28 CP + 30 AP) → commit → push → PR | ✅ |

---

## ⛔ HARD STOP — Pre-Dashboard Checklist

**Do not start Phase 7 until every item below is confirmed.**

| Checkpoint | Status |
|---|---|
| All 4 app containers start healthy (`docker compose up`) | ✅ |
| All 4 apps pass their full test suites | ✅ |
| All 4 log volumes contain real log entries | ✅ |
| FNOL ↔ Shared Data API integration verified end-to-end | ✅ |
| Agent Portal reads claims via Shared Data API correctly | ✅ |
| Shared Data API auth (JWT + API key) round-trips for FNOL/CP/AP | ✅ |
| All 4 app containers + 2 DBs stable together under load | ✅ |

---

## Phase 7 — Agentic Log Analysis Dashboard

Primary deliverable. FastAPI + React + LangChain + LangGraph + OpenAI + Chroma.
Reads logs from the four log volumes read-only. Conversational AI interface.

Decomposed into 5 sub-PRs with the LLM work deferred to the last two slices
(memory: `project_phase_7_subpr_sequence`). Each sub-PR gets its own Plan Mode
entry.

| Sub-PR | Scope | Status |
|---|---|---|
| **7a** | Scaffold (FastAPI + React + container) + standalone JWT auth (login + /me); fixes the placeholder log-dashboard service; adds the missing `shared-data-api-logs:/mnt/logs/shared-data-api:ro` mount; Swagger exposed for operator diagnostics | ✅ |
| **7b** | Log ingestion — read the 4 mounted volumes, parse each native format to a common shape, expose paginated/filterable `/api/logs` + `/api/status` | ✅ |
| **7c** | UI for the two non-AI screens — Overview Dashboard + Log Explorer wired to 7b's endpoints | ✅ |
| **7d** | Chroma + embeddings pipeline — vector-store-backed semantic search via `POST /api/logs/search`. WARN+ERROR / source=prod ingest filter, content-hash dedup, `DASHBOARD_INGEST_DRY_RUN` cost kill-switch, watcher + backfill respect both. | ✅ |
| **7e-PR4a** | LangGraph agent (StateGraph: ingest → analyze → correlate → predict → respond) + `POST /api/chat` + AI Chat UI + safe-by-default dry-run + credential redaction + LangSmith metadata. Bundled cross-cutting fix: X-Source propagation across all 4 apps (`structlog.contextvars` in SDA/FNOL, `AsyncLocalStorage` in CP, SLF4J `MDC` in AP) + outbound HTTP-client forwarding (FNOL/CP/AP → SDA carry the inbound source) + parser default → `unknown` so propagation gaps are operator-visible. Resolves the corpus mislabeling where 100% of WARN entries were tagged `prod` regardless of true origin. | ✅ |
| **7e-PR4b** | `GET /api/errors/{id}` + Error Detail UI; threads the agent into the Suggested Fix panel; SSE streaming on `/api/chat` (delete 422 branch, `graph.astream(stream_mode="updates")`, native fetch+ReadableStream on the client); content-hash IDs everywhere (`make_doc_id` swap in `parsers.py`); operator-facing level-count summary table printed after every OpenAI embed call. | ✅ |
| **7e-PR4c** | Proactive background scan (every N minutes) — surfaces anomalies automatically (shipped as PR #39; full detail in the "Phase 7 — Agitator Sequence" PR 4c row below) | ✅ |

---

## Phase 7 — Agitator Sequence (lead-in to 7e)

Four PRs that wire a programmatic load driver into the dashboard so it can
exercise the four apps and produce a representative WARN/ERROR corpus
without manual clicking. Designed 2026-06-04 (memory:
`project_agitator_design`).

| PR | Scope | Status |
|---|---|---|
| **PR 1** | Cross-app `X-Source` header convention — each app's request-logger middleware reads `X-Source` (default `prod`); Playwright configs set `X-Source: test`; ADR-011; parser precedence updated so health-path beats explicit. | ✅ |
| **PR 1.5** | Agent Portal — vendor Google Java Style ruleset to `apps/agent-portal/checkstyle.xml`, declare `maven-checkstyle-plugin` in `pom.xml` and bind to `verify` phase so `./mvnw -B verify` (the CI command) enforces it; pin `checkstyle 10.20.2` in the plugin dependency; AP code style cleanup. | ✅ |
| **PR 1.75** | Node prettier format gate — root `.prettierrc.json` (`printWidth: 100`, `endOfLine: lf`); each of the 5 Node packages (FNOL frontend, CP backend, CP frontend, AP frontend, dashboard frontend) declares `prettier ^3.8.3` + `format` / `format:check` scripts; per-app `ci-*.yml` runs `pnpm format:check` after `pnpm lint`; initial code-style sweep applied. | ✅ |
| **PR 1.9** | Code review enhancements (pre-PR-2) — `.claude/hooks/ship_audit.sh` invoked as `/ship` Step 1 (Node `format:check` + Python ruff/black + Java checkstyle phase binding + per-app `ci-*.yml` enforcement; fails closed, no `--skip`). Agentreviewer policy: model preference Opus 4.7, three-check pre-flight (`.env` gitignored, `.env.example` placeholder audit, hardcoded-secret grep), finding-triage workflow. Docs land in `.claude/rules/workflow.md` + `docs/development-workflow.md` + `CLAUDE.md`. No app code touched. | ✅ |
| **PR 1.95** | Consolidate CI workflows — replace 5 per-app `.github/workflows/ci-*.yml` files with a single `.github/workflows/ci.yml` containing a `dorny/paths-filter@v3` `changes` job + 5 conditional per-app jobs (same names, same steps, per-job concurrency). README badge row collapses 5 → 1. Cross-cutting PRs go from 5 workflow runs to 1; per-app PRs stay at 1. Memory updated for new branch-protection check names (`ci / <app>` prefix). No app code touched. | ✅ |
| **PR 2** | Chaos middleware — each of the 4 monitored apps (SDA/FNOL/CP/AP; dashboard exempt) gains a thin `X-Chaos: <directive>` middleware gated by `ENABLE_CHAOS=true` (default off). Directive grammar: `slow:<ms>` (0..60000) + `error:<status>` (400..599). Logs `chaos_honored` / `chaos_directive_invalid` at WARN so dashboard ingest picks them up. AP filter scoped to `/api/*` so `/actuator/health` is never chaosed. ADR-013. 20 new unit tests across the 4 apps. **First real exercise of agentreviewer** per the policy. | ✅ |
| **PR 3** | Agitator — bundled INTO the dashboard at `dashboard/src/log_dashboard/agitator/` + new screen `LogGenerator.tsx`. Operator-button-only bounded scenarios (auth-spike, payload-fuzz, policy-not-found, claim-burst, sda-degraded). `DASHBOARD_INGEST_SOURCES` default widens to `prod,synthetic`. ADR-014. 33 new dashboard backend tests + 10 new frontend tests. | ✅ |
| **PR 4** | Phase 7e first slice — LangGraph StateGraph + `POST /api/chat` + AI Chat UI; deferred to PR 4b (Error Detail) and PR 4c (proactive scan). ADR-015. ~30 new backend tests + 7 new frontend tests. Safe-by-default `DASHBOARD_LLM_DRY_RUN=true`. | ✅ |
| **PR 4b** | Phase 7e second slice — `GET /api/errors/{id}` + Error Detail UI. Threads the agent into the Suggested Fix panel via the same compiled graph used by `/api/chat`. SSE streaming on `/api/chat` (per-node status events). Stable content-hash `LogEntry.id` across the parser + Chroma. Embed-summary table after every OpenAI upsert. ADR-015 still applies. | ✅ |
| **PR 4c** | Phase 7e final slice — proactive background scan (every N minutes). Surfaces anomalies automatically through the existing agent graph + tool surface; findings ride on `/api/status` + render inline on the Overview screen. **Bundled:** chaos middleware level split (`chaos_honored` is ERROR on 5xx, WARN on 4xx + slow per ADR-013 2026-06-06 amendment) + new `error-burst` Agitator scenario. Extends `DASHBOARD_LLM_DRY_RUN` cost-safety to the background loop. ADR-016. Closes Phase 7. | ✅ |

---

## Phase 8 — Local AI: Replace OpenAI with Ollama

| Task | Status |
|---|---|
| **PR 8a** | Documentation + ADRs only (no behavior change). **NEW:** [`ADR-017-local-ai-via-ollama.md`](docs/decisions/ADR-017-local-ai-via-ollama.md) capturing the 8 Phase 8 design decisions (Ollama runtime, `llama3.1:8b` + `nomic-embed-text` model picks, Chroma wipe + re-embed migration, ingest level gate removal, 32GB Docker Desktop allocation, Ollama port internal-only, char-count tokenizer heuristic, chat-time system prompt). **Amendment blocks** on ADR-015 §5 (cost-asymmetry rescinded — `DRY_RUN` runtime default flips to false) and ADR-016 (cost matrix → fires/skips matrix). Doc surface updated across `CLAUDE.md`, `.claude/rules/dashboard.md` + `logging.md`, `README.md`, `docs/tech/*`, `docs/architecture/*` (incl. paired HTML diagrams), `docs/operations/dashboard-guide.md`, `docs/project-brief.md`. No code, no compose, no `.env.example` change. | ✅ |
| **PR 8b** | Implementation. `docker-compose.yml` gains `ollama` service + `ollama-data` volume + dashboard `depends_on`. `.env.example` drops `OPENAI_*` envs, adds `OLLAMA_BASE_URL` + `DASHBOARD_LLM_MODEL` + `DASHBOARD_EMBED_MODEL`. `pyproject.toml`: removes `langchain-openai` + `tiktoken`, adds `langchain-ollama`. Code call-sites swap (`ChatOpenAI` → `ChatOllama` in `agent/llm.py`; `OpenAIEmbeddings` → `OllamaEmbeddings` in `ingest/vectorstore.py`; `is_openai_api_error` → `is_llm_api_error` in `agent/responses.py`; `count_tokens` switches to `len(text) // 4` heuristic). Test rework (`fail_if_openai_invoked` → `fail_if_real_llm_invoked`; autouse `DASHBOARD_LLM_DRY_RUN=true` fixture; 503-message updates). Ingest level gate default flips to `DEBUG,INFO,WARN,ERROR`. `PROACTIVE_SCAN_PROMPT` revised for baseline awareness; `SystemMessage` injected at chat-time `analyze` node. Embed-summary table drops USD cost columns, adds wall-time. **Chroma wipe** (operator-driven, documented in dashboard-guide.md). Live-stack validation: full 36-spec Playwright sweep + smoke chat against real Ollama. | ⬜ |
