# Operating the Dashboard

Operator-facing runbook for the Agentic Log Analysis Dashboard. Covers the
Agitator load generator, chaos middleware, the embed-summary throughput
table, the Vectorstore Stats screen, and the Proactive Scan loop.

Design rationale lives in the ADRs cross-linked below
([ADR-013](../decisions/ADR-013-chaos-middleware.md),
[ADR-014](../decisions/ADR-014-agitator-bundled-into-dashboard.md),
[ADR-015](../decisions/ADR-015-langgraph-agent.md),
[ADR-016](../decisions/ADR-016-proactive-scan.md),
[ADR-017](../decisions/ADR-017-local-ai-via-ollama.md)).

> **Phase 8 / [ADR-017](../decisions/ADR-017-local-ai-via-ollama.md):** the
> dashboard now talks to a local Ollama container (`llama3.1:8b` for the
> LangGraph agent, `nomic-embed-text` for Chroma embeddings) instead of
> OpenAI. The embed-summary table reports tokens + wall-time (no USD);
> the ingest level gate is open by default (DEBUG ∪ INFO ∪ WARN ∪ ERROR)
> so the agent gains baseline awareness via RAG; and
> `DASHBOARD_LLM_DRY_RUN` defaults to `false` at runtime so AI Chat
> returns real responses out of the box.

> **How a log line travels from an app to the dashboard:**
> see [`docs/architecture/log-flow.md`](../architecture/log-flow.md) (or
> [`site/log-flow.html`](../../site/log-flow.html) for the visual diagram).
> That is the canonical reference for the FNOL → SDA → structlog → volume →
> watcher → ingest gate → Chroma pipeline. This document focuses on
> **operating** the dashboard once that pipeline is up.

Prerequisite: stack is up via `docker compose up -d` and the dashboard is
reachable at [http://localhost:4001/](http://localhost:4001/) with the admin
credentials from `.env`. First boot pulls ~5GB of Ollama models — 5–15 min
on M1 Max; cached on subsequent boots.

---

## Driving load with the Agitator

The Agitator runs bundled inside the dashboard — no separate process to deploy. Open
[http://localhost:4001/log-generator](http://localhost:4001/log-generator) after logging in
with the admin credentials from `.env`.

Ten built-in scenarios, one+ per app:

| Scenario | What it does | Logs produced | Needs chaos? |
|---|---|---|---|
| `auth-spike` | N login attempts with bad credentials against FNOL | WARN `login_failed` + `sda_upstream_rejected` (FNOL + SDA) | No |
| `payload-fuzz` | Malformed claim submissions against FNOL | WARN `request_validation_error` | No |
| `policy-not-found` | Reads against unknown policy numbers | WARN `policy_not_found` | No |
| `claim-burst` | Valid claim submissions at high rate | INFO `claim_created` | No |
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
(`DASHBOARD_INGEST_SOURCES=prod,synthetic,unknown`) admits it into Chroma. Playwright E2E
traffic gets `X-Source: test` which the same gate drops — so test runs don't pollute the
corpus. This is per [ADR-011](../decisions/ADR-011-x-source-header-convention.md).

---

## Chaos middleware (dev-only)

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

---

## Reading the embed-summary table

Every time the dashboard's watcher (or backfill) sends new log lines to Ollama for
embedding, you'll see a table in `docker compose logs log-dashboard`. Two representative
shapes from a live stack:

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
| INFO    |                1 |
| WARN    |                0 |
| ERROR   |                0 |
+---------+------------------+
| TOTAL   |                1 |
+---------+------------------+
| Tokens  |               44 |
| Wall    |            52 ms |
+---------+------------------+
 Session total (since startup): 6,980 tokens · 8,420 ms
========================================================
```

**Occasional coalesced batch — what you see during traffic bursts.** When new
lines arrive faster than the watcher's debounce window, the watcher buffers
and submits a multi-entry batch in one Ollama call:

```
========================================================
 Chroma embedding complete — customer-portal
========================================================
+---------+------------------+
| Level   |            Count |
+---------+------------------+
| DEBUG   |                0 |
| INFO    |                3 |
| WARN    |                0 |
| ERROR   |                0 |
+---------+------------------+
| TOTAL   |                3 |
+---------+------------------+
| Tokens  |              113 |
| Wall    |            68 ms |
+---------+------------------+
 Session total (since startup): 19,155 tokens · 22,400 ms
========================================================
```

**Throughput expectation.** Each `nomic-embed-text` call takes ~30–80ms on M1 Max
(varies with batch size and CPU pressure). A full Agitator + cross-app chaos run
(~340 entries across all 4 apps) embeds in a few seconds of cumulative wall time.
Phase 8 / ADR-017 — local inference is free, so the operator focuses on wall-time
budget, not USD.

- **Level rows:** count of entries per level that just hit the embedder. Phase 8
  default admits all 4 levels (DEBUG ∪ INFO ∪ WARN ∪ ERROR) so the agent gains
  baseline awareness via RAG.
- **TOTAL:** the count actually embedded in this batch (post-dedup; if a line was
  already in Chroma it doesn't appear here).
- **Tokens:** rough character-count heuristic (`len(text) // 4`). Operator-facing
  throughput proxy, not a billing meter.
- **Wall:** wall-clock milliseconds the batch's `store.add_documents` call took
  (includes Ollama embedding round-trip + Chroma write).
- **Session total:** cumulative since dashboard container startup. A restart resets
  these counters; durable signal lives in Chroma + the log volumes.

If `TOTAL` is zero, the operator never sees this table — there's no embed call to
summarise. Dry-run mode (`DASHBOARD_INGEST_DRY_RUN=true`) also short-circuits before
printing.

The same fields land in a structured `embedding_complete` log event for grep-ability:

```bash
docker compose logs log-dashboard | grep embedding_complete | jq -r \
  '"\(.app) batch=\(.batch_wall_ms)ms session=\(.session_wall_ms)ms"'
```

---

## What ends up in Chroma vs. the log volumes

| Surface | Reads | Filters | LLM traffic |
|---|---|---|---|
| `/api/logs`, `/api/status` (Log Explorer, Overview) | Log volumes directly | None | None |
| `/api/logs/search` (semantic search) | Chroma | All levels ∩ `prod`/`synthetic`/`unknown` | 1 embedding round-trip per query |
| `/api/errors/{id}` (Error Detail + Suggested Fix) | Chroma | Same source gate | One agent run per click — real LLM by default; dry-run via `DASHBOARD_LLM_DRY_RUN=true` |
| Proactive scan loop (opt-in) | Chroma | Same source gate | One agent run per cycle when `SCAN_ENABLED=true` AND `DRY_RUN=false` |

Phase 8 / ADR-017 — local Ollama inference is free, so traffic budgeting is about
wall-time + resource contention, not USD. The source gate still drops Playwright
`test` traffic and parser-derived `health` heartbeats — that's signal quality, not
cost control.

---

## Vectorstore Stats tab

Visit [http://localhost:4001/vectorstore-stats](http://localhost:4001/vectorstore-stats)
after logging in to see what's actually embedded in Chroma:

- Total document count + embedding model + vector dimensions (768 for `nomic-embed-text`)
- Breakdowns by app, level, source, top-10 events, and last-30-days time series
- Polls `GET /api/chroma/stats` every 30s; bar charts are pure Tailwind (no JS chart library)

Backed by `GET /api/chroma/stats` — a single `_collection.get(include=["metadatas"])` call;
no LLM traffic. 503 when the vectorstore is unavailable (`OLLAMA_BASE_URL` unreachable).

A "Vectorstore maintenance" panel on the same screen exposes `POST /api/chroma/flush` for
deleting every embedded document. The confirm dialog shows the current doc count + an
estimated wall-time to re-embed the same volume (~50ms per doc on M1 Max). After flush,
run `docker compose restart log-dashboard` to trigger the startup backfill task and
repopulate.

---

## Proactive Scan

The dashboard can scan the recent log corpus on a schedule and surface findings
inline on the Overview screen without anyone asking. Design rationale in
[ADR-016](../decisions/ADR-016-proactive-scan.md) (amended by ADR-017 — the
opt-in chain stays, the rationale shifts from cost-safety to scan-noise control).

**Opt-in chain** — BOTH must flip from default for real scans to fire:

| Env var | Default | Flip to | Effect |
|---|---|---|---|
| `DASHBOARD_LLM_DRY_RUN` | `false` (runtime) | `false` (default already) | Use real Ollama (canned response in dry-run) |
| `DASHBOARD_PROACTIVE_SCAN_ENABLED` | `false` | `true` | Start the background loop on dashboard boot |

Phase 8 / ADR-017 — `DASHBOARD_LLM_DRY_RUN` defaults to `false` at runtime, so the only
flag the operator typically flips is `DASHBOARD_PROACTIVE_SCAN_ENABLED`. Tests inherit
`DRY_RUN=true` via an autouse fixture so unit tests don't pay LLM latency.

Edit in `.env` (do not commit) and restart `log-dashboard`:

```bash
docker compose up -d --build log-dashboard
```

Either flag alone is safe:

- `DRY_RUN=true` + `SCAN_ENABLED=true` → loop wakes on schedule, logs
  `proactive_scan_skipped reason=llm_dry_run`, and goes back to sleep. Useful for
  verifying the loop scheduling without polluting the findings buffer with the
  fake's canned answer.
- `DRY_RUN=false` + `SCAN_ENABLED=false` → no loop. Chat still works
  (operator-driven, real Ollama).

**Tuning** (all optional, env defaults shown):

```
DASHBOARD_PROACTIVE_SCAN_INTERVAL_SECONDS=900   # 15 min — loop cadence (60..86400)
DASHBOARD_PROACTIVE_SCAN_LOOKBACK_MINUTES=30    # how far back each scan looks (5..1440)
DASHBOARD_PROACTIVE_SCAN_MAX_FINDINGS=5         # top-N surfaced on /api/status (1..20)
```

**Driving ERROR-tier signal on demand.** Once `ENABLE_CHAOS=true`, the
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

**Wall-time ballpark.** Each scan invokes the same compiled LangGraph used by
`/api/chat`. At PR 4a cost caps (≤4 tool calls + ≤2 LLM calls per scan) on
`llama3.1:8b`, expect ~15–60s per scan cycle on M1 Max. At a 15-min cadence
that's ~96 scans/day with ~30 min/day of cumulative LLM wall time. Raise the
interval to 1 hour for ~24 scans/day.
