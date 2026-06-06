# ADR-014: Agitator Bundled Into the Dashboard

**Status:** Accepted

## Decision

The Agitator — an operator-driven load generator that produces a representative WARN/ERROR corpus across SDA / FNOL / CP / AP — is **bundled into the dashboard** rather than shipped as a separate container. It lives at `dashboard/src/log_dashboard/agitator/` (Python module + scenario library) and `dashboard/frontend/src/pages/LogGenerator.tsx` (operator UI). New routes mount under `/api/agitator/*`. No new compose service, no new auth surface, no new image.

The Agitator's traffic is tagged with `X-Source: synthetic` so the four apps' loggers attribute the produced log lines to the Agitator. The dashboard's 7d ingest gate default widens to `DASHBOARD_INGEST_SOURCES=prod,synthetic`, so synthetic WARN/ERROR flows into Chroma alongside prod traffic.

## Context

The dashboard observes log volumes produced by the four monitored apps, but on a fresh `docker compose up` those volumes are empty (or contain only the system's own startup chatter). The PR 4 LangGraph agent (Phase 7e) needs a representative corpus of *interesting* WARN/ERROR signatures to be useful: auth failure pileups, validation rejections, induced chaos cascades.

The Agitator is the operator's lever to generate that corpus on demand. Two architectural questions had to be settled:

1. **Bundle into the dashboard, or ship as a separate container?**
2. **Auto-fire on startup, or operator-button-only?**

## Alternatives considered

### 1a. Separate `agitator` container

Pros: clear single-responsibility; the dashboard stays a pure consumer; the Agitator could be left running ambiently if we ever wanted continuous load.

Cons: another container, another image, another auth surface, another UI to log into. The dashboard's standalone JWT (ADR-006) would need a sibling Agitator JWT, or the dashboard would proxy auth to the Agitator (extra coupling). The demo flow (click → switch tabs → watch cards turn yellow) becomes "open two browser tabs" instead of one.

### 1b. Bundle into the dashboard (chosen)

Pros: one container, one auth, one UI. Reuses the dashboard's FastAPI scaffolding, React + Vite + Tailwind setup, JWT, structlog logger, LangSmith tracing wiring. The demo flow is genuinely better — single page, single login.

Cons: the dashboard is no longer a pure observer. **Mitigation:** the Agitator runs only on operator click, and scenarios are bounded in both request count and duration. If we ever need ambient continuous load, *that* is when a separate container becomes the right answer.

### 2a. Auto-fire scenarios on `docker compose up`

Pros: empty-corpus problem solved without operator action.

Cons: surprise OpenAI cost every restart (every embedding re-pays even if Chroma is partly populated, given the new entries); state-management complexity (first-run flag persisted where?); worse demo (the interesting moment — "click and watch logs flow" — is hidden behind a startup race).

### 2b. Operator-button-only (chosen)

Pros: every click = one bounded run. Cost is deterministic. State is in-memory only. Demo flow is genuinely "log in → click → watch."

Cons: empty-corpus state on first boot. **Mitigation:** the Overview gets a one-line `corpus_empty` banner with a "Open Log Generator" link.

## Operator-button-only invariant

- Scenarios are bounded: every scenario has a finite request count AND a finite duration. The runtime cap on both is enforced in `routers/agitator.py` via the `ScenarioSpec.params`.
- No lifespan hook starts a scenario.
- Concurrent runs are capped by `AGITATOR_MAX_CONCURRENT_RUNS` (default `2`).
- The same scenario cannot be double-launched while a prior run for it is `running`.
- Cancellation is `asyncio.Task.cancel()` — the worker drains, then the wrapper finalises the registry record as `cancelled`.

## Source-tag enforcement at a single seam

Every Agitator request goes through `agitator/http_client.py:build_client`, which sets `X-Source: synthetic` as a default header on the `httpx.AsyncClient`. Scenarios never construct their own clients. This is the *only* enforcement point — no scenario can drift.

The default `DASHBOARD_INGEST_SOURCES` widens from `{"prod"}` to `{"prod", "synthetic"}`. The level gate (`WARN, ERROR`) is unchanged — synthetic INFO is still dropped, so the `claim-burst` scenario's INFO floor doesn't enter Chroma.

`X-Source: test` (Playwright) and `X-Source: health` (parser-derived) remain excluded by default — the test/health vocabulary from ADR-011 still applies.

## Starter scenario pack

| Name | Target | Default count × duration | Produces | Needs chaos |
|---|---|---|---|---|
| `auth-spike` | FNOL | 50 × 30s | `login_failed` WARN in FNOL + SDA | No |
| `payload-fuzz` | FNOL | 100 × 60s | validation WARN in FNOL + SDA | No |
| `policy-not-found` | FNOL | 30 × 20s | 404 INFO traffic (not embedded — for /api/logs view) | No |
| `claim-burst` | FNOL | 200 × 60s | 201 INFO traffic + Postgres rows | No |
| `sda-degraded` | SDA | 240 × 120s | `chaos_honored` WARN cascade | **Yes** |
| `error-burst` | SDA | 120 × 60s | `chaos_honored` ERROR cascade (5xx → ERROR per ADR-013 amendment) | **Yes** |
| `cp-read-burst` | Customer Portal | 100 × 30s | INFO traffic at CP + SDA via `/policies/me` proxy reads | No |
| `cp-degraded` | Customer Portal | 80 × 60s | `chaos_honored` WARN cascade at CP | **Yes** |
| `ap-read-burst` | Agent Portal | 100 × 30s | INFO traffic at AP + SDA via `/api/claims` proxy reads | No |
| `ap-degraded` | Agent Portal | 80 × 60s | `chaos_honored` WARN cascade at AP | **Yes** |

`policy-not-found` produces INFO only — kept in the pack because operators benefit from seeing 404 traffic in the Log Explorer when validating filters, not because it drives the LangGraph corpus.

`cp-read-burst` and `ap-read-burst` similarly produce INFO only — they exist so every app has at least one non-chaos card on the Log Generator (operators can demo CP/AP working end-to-end without flipping `ENABLE_CHAOS`).

## Auth model

The Agitator uses each app's own login flow at scenario start:
- FNOL: `POST /auth/login` with `AGITATOR_CUSTOMER_USERNAME/PASSWORD`
- CP: `POST /auth/login` with the same customer creds
- AP: `POST /api/auth/login` with `AGITATOR_AGENT_USERNAME/PASSWORD`

JWTs land in an in-memory `AppSession` for the duration of the run. The session is never serialised onto the run-status response and never logged.

The `sda-degraded` scenario reaches SDA directly using `SHARED_DATA_API_KEY_CUSTOMER_PORTAL` + the CP-issued customer JWT (per ADR-005, the JWT is signed by SDA so it validates against SDA's auth layer). SDA's request log will show `caller=customer-portal`; the `source=synthetic` tag is the disambiguator. This is a deliberate trade-off: introducing a dedicated SDA caller identity for the Agitator would mean a new API key, a new SDA middleware allowlist entry, and a new env var — and `source=synthetic` already makes the provenance unambiguous.

## Run state

In-memory `RunRegistry` (bounded ring buffer, 50 entries). State lives only in-process; a dashboard restart loses run history. The corpus the runs produced is durable in Chroma + the apps' log volumes — that is what matters. Persistence is deferred until a concrete use case appears.

## Cost protection

The worst-case run (`payload-fuzz` 100 invalid POSTs producing 100 × WARN in SDA + 100 × WARN in FNOL = 200 lines) embeds 200 × ~$0.00002 ≈ $0.004 per run at `text-embedding-3-small` pricing. The content-hash dedup gate in `upsert_entries` ($ skipped if the line was previously embedded) keeps repeat runs near-zero. Total spend per demo session is bounded in the single-digit cents.

The Agitator's own log lines (`agitator_run_started`, `agitator_run_complete`) are at INFO, which is dropped by the default ingest gate — zero Chroma cost from the Agitator's own observability.

## Credential discipline

Per the project's NEVER LOG CREDENTIALS rule:
- `auth.py` logs login outcomes (`status`, `app`, `username`) but never passwords or tokens.
- `runs.py:_sanitize_error` strips credential-shaped tokens from `last_error` before storage.
- Run-status responses do not include any field from `AppSession`.

## References

- ADR-005 — Shared Data API as sole data layer (CP-issued JWTs work against SDA)
- ADR-006 — dashboard standalone JWT (still applies; Agitator routes use the same admin JWT)
- ADR-011 — `X-Source` header convention (Agitator uses `synthetic`)
- ADR-013 — chaos middleware (Agitator's `sda-degraded` drives it)
- Memory: `project_agitator_design` — the design notes that fed this ADR
- Memory: `project_agentreviewer_policy` — PR 3 is a named agentreviewer target
- `.claude/rules/dashboard.md` — Agitator section for runtime conventions
