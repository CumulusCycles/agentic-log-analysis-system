# Operating the Dashboard

Operator-facing runbook for the Agentic Log Analysis Dashboard. Covers the
Agitator load generator, chaos middleware, OpenAI embedding cost tracking,
the Vectorstore Stats screen, and the Proactive Scan loop.

Design rationale lives in the ADRs cross-linked below
([ADR-013](../decisions/ADR-013-chaos-middleware.md),
[ADR-014](../decisions/ADR-014-agitator-bundled-into-dashboard.md),
[ADR-015](../decisions/ADR-015-langgraph-agent.md),
[ADR-016](../decisions/ADR-016-proactive-scan.md),
[ADR-017](../decisions/ADR-017-local-ai-via-ollama.md)).

> **Phase 8 status (this PR is 8a — docs only):** [ADR-017](../decisions/ADR-017-local-ai-via-ollama.md) replaces OpenAI with locally-run Ollama in PR 8b. After PR 8b ships, the embed-summary "tokens + USD" cost table becomes "tokens + wall_ms" (local inference is free), the ingest level gate is removed (full-corpus embedding), and the `DASHBOARD_LLM_DRY_RUN` runtime default flips to `false`. Until PR 8b merges, the operational reality below — OpenAI cost tracking, WARN+ERROR-only Chroma corpus, dry-run-true default — describes the live system. PR 8b will rewrite this guide for the post-Phase-8 reality.

> **How a log line travels from an app to the dashboard:**
> see [`docs/architecture/log-flow.md`](../architecture/log-flow.md) (or
> [`log-flow.html`](../architecture/log-flow.html) for the visual diagram).
> That is the canonical reference for the FNOL → SDA → structlog → volume →
> watcher → ingest gate → Chroma pipeline. This document focuses on
> **operating** the dashboard once that pipeline is up.

Prerequisite: stack is up via `docker compose up -d` and the dashboard is
reachable at [http://localhost:4001/](http://localhost:4001/) with the admin
credentials from `.env`.

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
This is per [ADR-011](../decisions/ADR-011-x-source-header-convention.md).

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

---

## What ends up in Chroma vs. the log volumes

| Surface | Reads | Filters | Cost |
|---|---|---|---|
| `/api/logs`, `/api/status` (Log Explorer, Overview) | Log volumes directly | None | Zero — no OpenAI |
| `/api/logs/search` (semantic search) | Chroma | WARN+ERROR ∩ `prod`/`synthetic` only | OpenAI embed cost for ingestion + 1 query embedding per call |
| `/api/errors/{id}` (Error Detail + Suggested Fix) | Chroma | Same gate + WARN+ERROR only | One agent run per click — dry-run by default (`DASHBOARD_LLM_DRY_RUN=true`) |
| Proactive scan loop (opt-in) | Chroma | Same gate | One agent run per cycle when enabled AND `DRY_RUN=false` |

So healthcheck noise, Playwright E2E traffic, INFO success events, and full-dedup
restarts all cost **zero**. Real Chroma spend only happens when WARN+ERROR `prod` or
`synthetic` lines arrive that aren't already indexed.

---

## Vectorstore Stats tab

Visit [http://localhost:4001/vectorstore-stats](http://localhost:4001/vectorstore-stats)
after logging in to see what's actually embedded in Chroma:

- Total document count + embedding model + vector dimensions
- Breakdowns by app, level, source, top-10 events, and last-30-days time series
- Polls `GET /api/chroma/stats` every 30s; bar charts are pure Tailwind (no JS chart library)

Backed by `GET /api/chroma/stats` — a single `_collection.get(include=["metadatas"])` call;
no OpenAI traffic. 503 when the vectorstore is unavailable (placeholder `OPENAI_API_KEY`).

A "Vectorstore maintenance" panel on the same screen exposes `POST /api/chroma/flush` for
deleting every embedded document. The confirm dialog shows the current doc count + an
estimated OpenAI cost to re-embed the same volume. After flush, run
`docker compose restart log-dashboard` to trigger the startup backfill task and repopulate.

---

## Proactive Scan

The dashboard can scan the recent log corpus on a schedule and surface findings
inline on the Overview screen without anyone asking. Design rationale in
[ADR-016](../decisions/ADR-016-proactive-scan.md).

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
See [ADR-016](../decisions/ADR-016-proactive-scan.md) for the full cost analysis.
