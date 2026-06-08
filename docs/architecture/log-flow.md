# Log Flow — FNOL claim submit to dashboard

End-to-end path of a log line, from a user submitting a claim through the FNOL React app
to the dashboard's two reading surfaces — the unfiltered operator view and the filtered AI corpus.

For a visual rendering of the same flow, open [`log-flow.html`](log-flow.html) in a browser (HTML/CSS, not GitHub-rendered).

---

## The 10 steps

### 1. Browser → FNOL backend

User submits the claim form in the React SPA. The frontend POSTs to `http://localhost:8001/fnol/submit` with `Authorization: Bearer <jwt>` and `X-Source: prod` (explicitly set by the SPA's fetch wrapper per [ADR-011](../decisions/ADR-011-x-source-header-convention.md) amendment).

> **Code:** `apps/fnol/frontend/src/lib/api.ts`

### 2. FNOL request-logger middleware (inbound)

A FastAPI middleware reads `X-Source` and **binds it onto `structlog.contextvars`** so every domain event during the request lifetime inherits the source label. It emits a structured `event=request` line with `caller`, `user`, `method`, `path`, `status`, `duration_ms`, `source` — never the token or password.

> **Code:** `apps/fnol/src/fnol/middleware/request_logger.py`
> **Rules:** [`.claude/rules/logging.md`](../../.claude/rules/logging.md) §Non-Negotiable Rules; [ADR-011](../decisions/ADR-011-x-source-header-convention.md)

### 3. FNOL → Shared Data API

The `/fnol/submit` handler builds the SDA `POST /claims` request with three headers:

- `X-API-Key: $SHARED_DATA_API_KEY_FNOL` — inter-service auth
- `Authorization: Bearer <user-jwt>` — forwarded from the original request
- `X-Source: <value>` — read from the structlog contextvar so SDA's logs carry the same source

SDA validates both auth headers, **enforces `jwt.app == "fnol"`** as defense-in-depth against cross-app token replay (per [ADR-006](../decisions/ADR-006-auth-strategy.md)), inserts the claim row into Postgres, and logs its own request line. Non-2xx from SDA → FNOL logs `sda_upstream_rejected` (WARN) with `detail` parsed from the response body, never from response headers (which could echo `Authorization` / `X-API-Key`).

> **Code:** `apps/fnol/src/fnol/routers/claims.py`; `apps/shared-data-api/src/shared_data_api/services/claims_service.py`
> **Event catalog:** [`docs/tech/log-events.md`](../tech/log-events.md) §FNOL §WARN

### 4. structlog routes to two sinks

FNOL's logger is configured with `logging.basicConfig` + `structlog.configure` (with the mandatory `cache_logger_on_first_use=False` per `reference_structlog_cache_logger_off`). Two handlers attached:

- **stdout** — visible via `docker compose logs fnol-app`
- **`RotatingFileHandler`** — `/app/logs/fnol-app.log` (10 MB cap, 5 backups)

Both sinks emit the identical JSON line. Exception tracebacks emit as multi-line plain text on the same handlers.

> **Code:** `apps/fnol/src/fnol/logging_setup.py`

### 5. File path is a Docker volume

`docker-compose.yml` mounts `fnol-logs:/app/logs` for the `fnol-app` service. Writes to `/app/logs/fnol-app.log` land on the named volume on the host — survive container restarts, live in Docker's volume store.

> **Compose:** `docker-compose.yml#fnol-app`

### 6. Dashboard mounts the same volume — read-only

The `log-dashboard` service mounts `fnol-logs:/mnt/logs/fnol:ro`. The exact same bytes FNOL wrote are visible at `/mnt/logs/fnol/fnol-app.log` inside the dashboard container — the `:ro` is enforced by the kernel.

> **Compose:** `docker-compose.yml#log-dashboard`

### 7a. Human path — `/api/logs` + `/api/status`

The Log Explorer and Overview screens call these routes. The handler reads the log file directly from `/mnt/logs/fnol/fnol-app.log` via the tail reader. **No ingest gate.** The operator always sees every INFO line, every health-probe entry, every Playwright test request.

> **Code:** `dashboard/src/log_dashboard/routers/logs.py`; `dashboard/src/log_dashboard/ingest/reader.py`

### 7b. AI path — watchdog observer

`LogVolumeWatcher` schedules a `watchdog.Observer` on `/mnt/logs/fnol/`. On `on_modified` for `fnol-app.log`:

- Reads from the per-file byte offset (kept in-process) to EOF
- Parses each new line via the FNOL structlog parser → `LogEntry`
- Hands off to step 8b

> **Code:** `dashboard/src/log_dashboard/ingest/watcher.py`

### 8b. Parser + source inference

`_infer_source` precedence (in order):

1. `event=request` and path ∈ `{/health, /api/health, /actuator/health}` → `"health"` (beats explicit — path cannot be overridden by a header)
2. Explicit `source=<value>` in the log line → honored
3. Otherwise → **`"unknown"`**

Step 3 is the [ADR-011 amendment](../decisions/ADR-011-x-source-header-convention.md) (2026-06-07): React SPAs explicitly tag `prod`; anything missing the header lands in `unknown` as a propagation-gap signal.

> **Code:** `dashboard/src/log_dashboard/ingest/parsers.py:_infer_source`

### 9. 3-knob ingest gate

The gate runs in two seams, both BEFORE any OpenAI embed call:

| Knob | Default | Where it's checked |
|---|---|---|
| `DASHBOARD_INGEST_LEVELS` | `WARN,ERROR` | `filter_for_ingest(entries, *, levels, sources)` keeps iff `entry.level in levels` |
| `DASHBOARD_INGEST_SOURCES` | **`prod,synthetic,unknown`** | Same `filter_for_ingest` — keeps iff `entry.source in sources` |
| `DASHBOARD_INGEST_DRY_RUN` | `false` | `upsert_entries(..., dry_run=...)` short-circuits at `if not entries or dry_run` before any Chroma read or OpenAI call |

A successful claim submission (INFO) is dropped by `filter_for_ingest` — never embedded, zero token cost. An SDA upstream rejection (WARN, `source=prod`) passes. A propagation-gap WARN (`source=unknown`) also passes — the operator can see drift in the corpus.

> **Code:** `dashboard/src/log_dashboard/ingest/embeddings.py:filter_for_ingest`; `dashboard/src/log_dashboard/ingest/vectorstore.py:upsert_entries`; `dashboard/src/log_dashboard/config.py`; `.env.example`

### 10. Dedup → OpenAI → Chroma

For surviving entries, `upsert_entries` queries Chroma for `fnol:{sha1(raw)[:16]}` IDs (content-hash). Two cheap calls in the path:

- `_collection.get(ids=[...], include=[])` — existence check, no payload returned
- For genuinely new IDs only: OpenAI `text-embedding-3-small` batch call → vectors

The vectors land in the `dashboard-logs` collection in the `chroma-data` volume. Same line twice = same content hash = single Chroma row. After the embed, an embedding-summary table prints to stdout (operator-visible cost tracking).

> **Code:** `dashboard/src/log_dashboard/ingest/vectorstore.py`
> **Collection default:** `dashboard-logs` (`config.py:chroma_collection`)
> **Cost tracking:** see [`docs/operations/dashboard-guide.md`](../operations/dashboard-guide.md) §Reading the embed-summary table

### 11. Agent surfaces

Chroma is the corpus for:

- `POST /api/logs/search` — semantic search
- `GET /api/errors/{id}` — Error Detail + Suggested Fix (single agent run per click)
- `POST /api/chat` — AI Chat LangGraph StateGraph
- Proactive scan loop — opt-in, every 15 min by default
- `GET /api/chroma/stats` — Vectorstore Stats screen (aggregate counts, no OpenAI)

Two independent reading paths over the same source bytes — the human path (`/api/logs`, unfiltered) and the AI path (Chroma, filtered + deduped).

---

## What changed since the original walkthrough

- **Source default flipped from `prod` to `unknown`** (step 8b) — [ADR-011](../decisions/ADR-011-x-source-header-convention.md) amendment 2026-06-07 (PR #42). React SPAs now explicitly tag `X-Source: prod`; the missing-header default is `unknown` as a propagation-gap signal.
- **Ingest gate sources widened to `prod,synthetic,unknown`** (step 9) — admits Agitator traffic AND the propagation-gap signal so the operator can spot drift in the corpus.
- **JWT app-claim defense-in-depth lives in [ADR-006](../decisions/ADR-006-auth-strategy.md)**, not ADR-007 (ADR-007 is the background claim-status simulator).
- **The file handler is `RotatingFileHandler`** (10 MB cap, 5 backups), not a plain `FileHandler` — log rotation is automatic.

---

## Reference index

| Concern | Path |
|---|---|
| Auth + JWT defense-in-depth | [ADR-006](../decisions/ADR-006-auth-strategy.md) |
| `X-Source` header convention + 2026-06-07 amendment | [ADR-011](../decisions/ADR-011-x-source-header-convention.md) |
| Logging strategy (per-stack formats, volumes, NEVER LOG CREDENTIALS) | [`docs/tech/logging-strategy.md`](../tech/logging-strategy.md) |
| Event catalog (every structured event emitted by the four apps) | [`docs/tech/log-events.md`](../tech/log-events.md) |
| FNOL request logger (binds X-Source to contextvars) | `apps/fnol/src/fnol/middleware/request_logger.py` |
| FNOL logging setup (two sinks) | `apps/fnol/src/fnol/logging_setup.py` |
| SDA claims service (`jwt.app == "fnol"` check) | `apps/shared-data-api/src/shared_data_api/services/claims_service.py` |
| Dashboard tail reader | `dashboard/src/log_dashboard/ingest/reader.py` |
| Dashboard watchdog observer | `dashboard/src/log_dashboard/ingest/watcher.py` |
| Dashboard parser + source inference | `dashboard/src/log_dashboard/ingest/parsers.py` |
| Dashboard vectorstore (Chroma upsert + dedup) | `dashboard/src/log_dashboard/ingest/vectorstore.py` |
| Operator runbook (cost tracking, Vectorstore Stats, scan) | [`docs/operations/dashboard-guide.md`](../operations/dashboard-guide.md) |
