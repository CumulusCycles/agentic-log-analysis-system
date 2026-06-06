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
| 7c | Dashboard UI — Overview + Log Explorer screens | ✅ |
| 7d | Dashboard semantic search — Chroma + embeddings pipeline + ingest filter (WARN/ERROR/prod by default) + `POST /api/logs/search` | ✅ |
| Agitator PR 1 | Cross-app `X-Source` header convention — middleware + Playwright configs + ADR-011 | ✅ |
| Agitator PR 1.5 | Agent Portal — project checkstyle ruleset (Google Java Style + overrides) + CI binding via `verify` phase + code style cleanup | ✅ |
| Agitator PR 1.75 | Node prettier format gate — root config + per-package scripts + CI binding across all 5 Node packages | ✅ |
| Agitator PR 1.9 | Code review enhancements — `/ship` Step 1 tool-enforcement audit (`.claude/hooks/ship_audit.sh`) + agentreviewer policy (`/ultrareview` for high-stakes PRs, Opus 4.7 preference, pre-flight checks) | ✅ |
| Agitator PR 1.95 | Consolidate CI workflows — single `ci.yml` with `paths-filter` `changes` job + 5 conditional per-app jobs; cross-cutting PRs go 5 runs → 1; README badge row collapses 5 → 1 | ✅ |
| Agitator PR 2 | Chaos middleware — `X-Chaos: slow:<ms>` / `error:<status>` across SDA/FNOL/CP/AP, `ENABLE_CHAOS` env gate, dashboard exempt | ✅ |
| Agitator PR 3 | Agitator bundled into dashboard — operator-triggered bounded scenarios (auth-spike, payload-fuzz, policy-not-found, claim-burst, sda-degraded); `X-Source: synthetic` tagging; new `/log-generator` UI; ADR-014 | ✅ |
| 7e-PR4a | Dashboard LangGraph agent — `POST /api/chat` + AI Chat UI; 5-node StateGraph; safe-by-default dry-run; credential redaction; LangSmith metadata; ADR-015. Bundled cross-cutting X-Source propagation across SDA/FNOL/CP/AP (contextvars / AsyncLocalStorage / MDC) + outbound HTTP-client forwarding so SDA's WARN/ERROR domain events carry the originating source — Chroma can now distinguish prod/synthetic/test instead of mislabeling everything as prod | ✅ |
| 7e-PR4b | Dashboard `GET /api/errors/{id}` + Error Detail UI; threads agent into Suggested Fix via the same compiled graph as `/api/chat`; SSE streaming on `/api/chat` with per-node status events; content-hash `LogEntry.id` everywhere; embed-summary table after every OpenAI upsert | ✅ |
| 7e-PR4c | Dashboard proactive background scan — surfaces anomalies automatically on the Overview screen. Bundled: chaos middleware level split (5xx → ERROR per ADR-013 amendment) + new `error-burst` Agitator scenario. ADR-016. Closes Phase 7. | ✅ |

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

## Operating the dashboard

Once the stack is up, the dashboard exposes a `/log-generator` screen that lets an operator
drive bounded load against the four monitored apps so the agent has something to analyse.
This section is the user-facing operator guide; design rationale lives in
[ADR-014](docs/decisions/ADR-014-agitator-bundled-into-dashboard.md) and
[ADR-013](docs/decisions/ADR-013-chaos-middleware.md).

### Driving load with the Agitator

The Agitator runs bundled inside the dashboard — no separate process to deploy. Open
[http://localhost:4001/log-generator](http://localhost:4001/log-generator) after logging in
with the admin credentials from `.env`.

Ten built-in scenarios, one+ per app:

| Scenario | What it does | Logs produced | Needs chaos? |
|---|---|---|---|
| `auth-spike` | N login attempts with bad credentials against FNOL | WARN `login_failed` + `sda_upstream_rejected` (FNOL + SDA) | No |
| `payload-fuzz` | Malformed claim submissions against FNOL | WARN `request_validation_error` | No |
| `policy-not-found` | Reads against unknown policy numbers | WARN `policy_not_found` | No |
| `claim-burst` | Valid claim submissions at high rate | INFO `claim_created` (filtered from Chroma) | No |
| `sda-degraded` | 240 reads with `X-Chaos: slow:500` over 120s | WARN `chaos_honored` | **Yes** — see below |
| `error-burst` | 120 reads with `X-Chaos: error:500` over 60s | ERROR `chaos_honored` (5xx → ERROR per ADR-013 amendment) | **Yes** |
| `cp-read-burst` | 100 GETs against CP `/policies/me` over 30s | INFO at CP + SDA (no DB writes) | No |
| `cp-degraded` | 80 GETs against CP `/policies/me` with `X-Chaos: slow:300` over 60s | WARN `chaos_honored` at CP | **Yes** |
| `ap-read-burst` | 100 GETs against AP `/api/claims` over 30s | INFO at AP + SDA (no DB writes) | No |
| `ap-degraded` | 80 GETs against AP `/api/claims` with `X-Chaos: slow:300` over 60s | WARN `chaos_honored` at AP | **Yes** |

Every scenario is **operator-button-only** — never auto-fires. Each scenario is bounded
(finite count + finite duration). Cancellation is a single click; the global cap is 2
concurrent runs. Run history persists in-memory only — the dashboard restart clears it,
which is fine because the durable signal lives in Chroma + the log volumes.

Every Agitator request tags `X-Source: synthetic` so the dashboard's ingest gate
(`DASHBOARD_INGEST_SOURCES=prod,synthetic`) admits it into Chroma. Playwright E2E traffic
gets `X-Source: test` which the same gate drops — so test runs don't pollute the corpus.
This is per [ADR-011](docs/decisions/ADR-011-x-source-header-convention.md).

### Chaos middleware (dev-only)

The `sda-degraded` scenario above — and any direct `curl` with `X-Chaos: slow:<ms>` or
`X-Chaos: error:<status>` — only fires when **each app** has `ENABLE_CHAOS=true` in its
container env. The dashboard itself is exempt (it's the observer, not a target).

**To enable:**

1. Edit `.env` and set `ENABLE_CHAOS=true`
2. Restart only the chaos-aware containers (no need to recycle Chroma / Postgres / Mongo /
   dashboard):
   ```bash
   docker compose up -d shared-data-api fnol-app customer-portal agent-portal
   ```
3. The `/log-generator` UI un-greys the `sda-degraded` card once it sees the new state.

**To disable:** flip back to `ENABLE_CHAOS=false` and re-run the same `docker compose up
-d` command. The default is `false` — flip it back when done experimenting.

The chaos middleware sits behind auth at every app (SDA: after `APIKeyMiddleware`; AP:
`FilterRegistrationBean` order 20 > JWT order 1) so chaos cannot bypass security. AP scopes
chaos to `/api/*` only, so `/actuator/health` is never disturbed.

### Reading the embed-summary table

Every time the dashboard's watcher (or backfill) sends new log lines to OpenAI for
embedding, you'll see a table in `docker compose logs log-dashboard`. Two real shapes
captured during a 2026-06-06 live validation run illustrate what to expect.

**Typical (size-1) batch — what you see most of the time.** The file watcher
fires once per new log line, so most batches contain a single entry:

```
========================================================
 Chroma embedding complete — shared-data-api
========================================================
+---------+------------------+
| Level   |            Count |
+---------+------------------+
| DEBUG   |                0 |
| INFO    |                0 |
| WARN    |                0 |
| ERROR   |                1 |
+---------+------------------+
| TOTAL   |                1 |
+---------+------------------+
| Tokens  |               44 |
| Cost    |        $0.000001 |
+---------+------------------+
 Session total (since startup): 6,980 tokens · $0.000140
========================================================
```

**Occasional coalesced batch — what you see during traffic bursts.** When new
lines arrive faster than the watcher's debounce window, the watcher buffers
and submits a multi-entry batch in one OpenAI call:

```
========================================================
 Chroma embedding complete — customer-portal
========================================================
+---------+------------------+
| Level   |            Count |
+---------+------------------+
| DEBUG   |                0 |
| INFO    |                0 |
| WARN    |                0 |
| ERROR   |               20 |
+---------+------------------+
| TOTAL   |               20 |
+---------+------------------+
| Tokens  |              920 |
| Cost    |        $0.000018 |
+---------+------------------+
 Session total (since startup): 19,155 tokens · $0.000383
========================================================
```

**Cost expectation.** A full Agitator + cross-app chaos run (~340 WARN+ERROR
lines across all 4 apps) costs about **$0.0006** in embedding tokens on
`text-embedding-3-small`. Ongoing steady-state traffic in normal operation
is far less — most batches are size 1 and the per-batch cost rounds to a
fraction of a cent.

- **Level rows:** count of entries per level that just hit OpenAI. Only WARN + ERROR are
  embedded by default — the `DASHBOARD_INGEST_LEVELS=WARN,ERROR` gate drops INFO/DEBUG
  before the embedder is called.
- **TOTAL:** the count actually paid for in this batch (post-dedup; if a line was already in
  Chroma it doesn't appear here).
- **Tokens + Cost:** computed via `tiktoken cl100k_base` × `text-embedding-3-small` list
  price ($0.02 per 1M tokens — update the constant in
  `dashboard/src/log_dashboard/ingest/vectorstore.py` if OpenAI re-prices).
- **Session total:** cumulative since dashboard container startup. A restart resets this
  counter (the spend itself doesn't persist anywhere durable).

If `TOTAL` is zero, the operator never sees this table — there's no embed call to
summarise. Dry-run mode (`DASHBOARD_INGEST_DRY_RUN=true`) also short-circuits before
printing.

The same fields land in a structured `embedding_complete` log event for grep-ability:

```bash
docker compose logs log-dashboard | grep embedding_complete | jq -r \
  '"\(.app) batch=$\(.batch_cost_usd) session=$\(.session_cost_usd)"'
```

### What ends up in Chroma vs. the log volumes

| Surface | Reads | Filters | Cost |
|---|---|---|---|
| `/api/logs`, `/api/status` (Log Explorer, Overview) | Log volumes directly | None | Zero — no OpenAI |
| `/api/logs/search` (semantic search) | Chroma | WARN+ERROR ∩ `prod`/`synthetic` only | OpenAI embed cost for ingestion + 1 query embedding per call |
| `/api/errors/{id}` (Error Detail + Suggested Fix) | Chroma | Same gate + WARN+ERROR only | One agent run per click — dry-run by default (`DASHBOARD_LLM_DRY_RUN=true`) |
| Proactive scan loop (PR 4c — opt-in) | Chroma | Same gate | One agent run per cycle when enabled AND `DRY_RUN=false` |

So healthcheck noise, Playwright E2E traffic, INFO success events, and full-dedup
restarts all cost **zero**. Real Chroma spend only happens when WARN+ERROR `prod` or
`synthetic` lines arrive that aren't already indexed.

### Vectorstore Stats tab

Visit [http://localhost:4001/vectorstore-stats](http://localhost:4001/vectorstore-stats)
after logging in to see what's actually embedded in Chroma:

- Total document count + embedding model + vector dimensions
- Breakdowns by app, level, source, top-10 events, and last-30-days time series
- Polls `GET /api/chroma/stats` every 30s; bar charts are pure Tailwind (no JS chart library)

Backed by `GET /api/chroma/stats` — a single `_collection.get(include=["metadatas"])` call;
no OpenAI traffic. 503 when the vectorstore is unavailable (placeholder `OPENAI_API_KEY`).

### Proactive Scan (PR 4c)

The dashboard can scan the recent log corpus on a schedule and surface findings
inline on the Overview screen without anyone asking. This closes Phase 7.

**Opt-in chain** — BOTH must flip from default for real scans to fire:

| Env var | Default | Flip to | Effect |
|---|---|---|---|
| `DASHBOARD_LLM_DRY_RUN` | `true`  | `false` | Use real OpenAI (canned response in dry-run) |
| `DASHBOARD_PROACTIVE_SCAN_ENABLED` | `false` | `true`  | Start the background loop on dashboard boot |

Edit both in `.env` (do not commit) and restart `log-dashboard`:

```bash
docker compose up -d --build log-dashboard
```

Either flag alone is safe:

- `DRY_RUN=true` + `SCAN_ENABLED=true` → loop wakes on schedule, logs
  `proactive_scan_skipped reason=llm_dry_run`, and goes back to sleep — zero cost.
  Useful for verifying the loop scheduling without paid spend.
- `DRY_RUN=false` + `SCAN_ENABLED=false` → no loop. Chat still works
  (operator-driven, real OpenAI). No background spend.

**Tuning** (all optional, env defaults shown):

```
DASHBOARD_PROACTIVE_SCAN_INTERVAL_SECONDS=900   # 15 min — loop cadence (60..86400)
DASHBOARD_PROACTIVE_SCAN_LOOKBACK_MINUTES=30    # how far back each scan looks (5..1440)
DASHBOARD_PROACTIVE_SCAN_MAX_FINDINGS=5         # top-N surfaced on /api/status (1..20)
```

**Driving ERROR-tier signal on demand.** Once `ENABLE_CHAOS=true`, the new
`error-burst` Agitator scenario sends `X-Chaos: error:500` against SDA `/policies`.
The chaos middleware logs `chaos_honored` at ERROR (5xx → ERROR per ADR-013
2026-06-06 amendment), the ingest gate admits it into Chroma, and the next scan
cycle picks it up. Click **Log Generator → Error burst** in the dashboard.

**Reading findings.** When a scan finds an anomaly, it appears as a card on the
Overview screen above the per-app status grid:

- Severity pill (info/warn/error) — color-coded from the underlying citation levels
- 1–2 sentence summary from the agent
- Citation links — each click navigates to `/errors/:id` for the agent's per-error
  Suggested Fix analysis

Findings are restart-lossy by design — same posture as Agitator runs. The
durable signal lives in Chroma + the log volumes.

**Cost ballpark.** With both flags on at 15-min cadence, expect ~96 scans/day.
At gpt-4o list prices and PR 4a cost caps (≤4 tool calls + ≤2 LLM calls per
scan), worst case is ~$3/day. Raise the interval to 1 hour for ~$0.72/day.
See ADR-016 for the full cost analysis.

---

## Development Workflow

- **Branch:** always `feature/<name>` or `fix/<name>` — never commit to `main`
- **Commit:** conventional commits scoped to the app — `feat(fnol):`, `fix(customer-portal):`
- **Ship:** run `/ship` — lints, builds, commits, pushes, opens PR
- **Done:** run `/done` after merge — checks out main, pulls, deletes both local and remote branches, removes orphaned PR-time CI runs

See `.claude/rules/workflow.md` for the complete pre-ship checklist.

## Contributions

🤖 This project was built in collaboration with [**Claude Code**](https://www.anthropic.com/product/claude-code).
