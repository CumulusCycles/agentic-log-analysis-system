# Project Rules — Agentic Log Analysis Dashboard

## Purpose
The primary deliverable. An agentic AI system that will continuously monitor logs from all
four logging apps (Shared Data API, FNOL, Customer Portal, Agent Portal), identify issues,
suggest remediation, and proactively predict problems before they escalate.

---

## Stack
- **Backend**: Python 3.12 / FastAPI (`uv`)
- **Frontend**: React 18 + Vite + TypeScript (`pnpm`)
- **AI Framework**: LangChain + LangGraph
- **LLM**: OpenAI (`gpt-4o` for analysis, `text-embedding-3-small` for embeddings)
- **Vector Store**: Chroma (persistent Docker container)
- **Observability**: LangSmith (trace every agent run)
- **Log ingestion**: `watchdog` file watcher → embeds entries into Chroma continuously
- **Single container**: FastAPI serves React build as static files
- **Standalone auth**: local JWT signed with `DASHBOARD_JWT_SECRET`; admin credentials from env (`DASHBOARD_ADMIN_USERNAME` / `DASHBOARD_ADMIN_PASSWORD`). Independent of the Shared Data API — the dashboard must function for diagnostics when SDA is down. See ADR-006.

---

## Agent Architecture (LangGraph StateGraph)
- **Nodes**: ingest → analyze → correlate → predict → respond
- **Tools**: `query_logs` (Chroma semantic search), `get_app_status`
- **Memory**: conversation history persisted per session
- **Proactive loop**: background run every N minutes, surfaces anomalies automatically

---

## UI Screens
- **Overview Dashboard** (7c ✅): per-app status cards (ok / degraded / error), 1h/24h/7d INFO/WARN/ERROR counts, polled every 15 s; click a card to drill down to the Log Explorer pre-filtered to that app.
- **Log Explorer** (7c ✅): paginated/filterable log table (app, level, time-window preset 1h/24h/7d), row click expands `fields` + raw line inline, `next_before` cursor pagination. Semantic search is deferred to 7d.
- **AI Chat** (7e): conversational interface for root cause + remediation
- **Error Detail** (7e): full raw log, stack trace, LangGraph analysis panel, suggested fix

---

## Container Config
- Service name: `log-dashboard` · Internal port: 4000 / Host port: 4001
- Health endpoint: `GET /health` · Platform: `linux/arm64`
- Depends on: `chroma` (service_healthy)

## Chroma Container Config
- Service name: `chroma` · Image: `chromadb/chroma:1.5.9`
- Internal port: 8000 (internal only — not exposed to host)
- Volume: `chroma-data:/chroma/chroma`
- Env: `IS_PERSISTENT=TRUE`, `PERSIST_DIRECTORY=/chroma/chroma`

---

## Volume Access — READ-ONLY
```yaml
volumes:
  - shared-data-api-logs:/mnt/logs/shared-data-api:ro
  - fnol-logs:/mnt/logs/fnol:ro
  - customer-portal-logs:/mnt/logs/customer-portal:ro
  - agent-portal-logs:/mnt/logs/agent-portal:ro
```

## Environment Variables
- `OPENAI_API_KEY`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `DASHBOARD_CHROMA_URL`
- `DASHBOARD_JWT_SECRET`, `DASHBOARD_ADMIN_USERNAME`, `DASHBOARD_ADMIN_PASSWORD` (standalone auth)

---

## Directory Layout
```
dashboard/
├── main.py              # FastAPI entry point
├── pyproject.toml       # Python deps (uv)
├── tests/               # pytest test suite
└── frontend/            # React + Vite + TypeScript (pnpm)
    ├── package.json
    └── src/
```
Backend (`uv run pytest`) runs from `dashboard/`.
Frontend (`pnpm test`) runs from `dashboard/frontend/`.

---

## Routes

Phase 7 is sub-PR'd into 5 slices (memory: `project_phase_7_subpr_sequence`).
Routes land incrementally:

| Method | Path | Purpose | Phase |
|---|---|---|---|
| `GET` | `/health` | Container healthcheck | 7a ✅ |
| `POST` | `/api/auth/login` | Admin login → JWT (standalone, independent of SDA) | 7a ✅ |
| `GET` | `/api/auth/me` | Current admin from JWT | 7a ✅ |
| `GET` | `/api/status` | Per-app status cards for Overview Dashboard | 7b ✅ |
| `GET` | `/api/logs` | Paginated log entries for Log Explorer | 7b ✅ |
| `POST` | `/api/logs/search` | Semantic search over Chroma — body: query + filter clauses; returns LogEntry[] + scores | 7d ✅ |
| `GET` | `/api/agitator/scenarios` | List available Agitator scenarios | PR 3 ✅ |
| `GET` | `/api/agitator/env` | Report `ENABLE_CHAOS` so the UI can gate chaos-only cards | PR 3 ✅ |
| `POST` | `/api/agitator/runs` | Start a bounded scenario run | PR 3 ✅ |
| `GET` | `/api/agitator/runs` | List recent (up to 50) Agitator runs | PR 3 ✅ |
| `GET` | `/api/agitator/runs/{run_id}` | Poll one run's counters | PR 3 ✅ |
| `POST` | `/api/agitator/runs/{run_id}/cancel` | Cancel an in-flight run | PR 3 ✅ |
| `POST` | `/api/chat` | AI Chat — submit question, get LangGraph response. `streaming: true` upgrades the response to SSE: one `event: node` per agent node, terminating `event: complete` mirrors the JSON `ChatResponse` shape. Pre-flight rejections (401 / 413 / 503) still return JSON. | 7e (PR 4a + 4b SSE) ✅ |
| `GET` | `/api/errors/{id}` | Full error detail + LangGraph "Suggested Fix". JWT-gated. ID shape: `{app}:{sha1(raw)[:16]}` (same as Chroma doc ID). 400 on malformed ID; 404 when the entry isn't in Chroma (only WARN+ERROR pass the ingest gate); 503 when OPENAI_API_KEY is the placeholder. | 7e (PR 4b) ✅ |
| `GET` | `/api/chroma/stats` | Aggregated stats over the Chroma collection — total count, by_app, by_level, by_source, by_event (top 10), by_day (last 30 days). Single `_collection.get(include=["metadatas"])` call; no OpenAI. 503 when vectorstore unavailable. Backs the Vectorstore Stats tab. | post-7e ✅ |

Swagger UI (`/docs`, `/redoc`, `/openapi.json`) is exposed — the dashboard's
audience is the admin/operator, and Swagger is a strict diagnostic win.
Anonymous browser load mirrors SDA; calling endpoints still requires JWT via
the Authorize button. ADR-001 local-only threat model applies.

> Dashboard auth does NOT depend on the Shared Data API being healthy — by design.
> Local-only JWT keeps the diagnostic tool usable when the apps it observes are sick.

---

## Ingest Gate (Phase 7d)

Backfill + watcher both apply a 3-knob filter BEFORE any OpenAI embedding call.
The operator-facing `/api/logs` view reads volumes directly and is UNAFFECTED.

| Knob | Default | Where set |
|---|---|---|
| `DASHBOARD_INGEST_LEVELS` | `WARN,ERROR` | `.env` (CSV) |
| `DASHBOARD_INGEST_SOURCES` | `prod,synthetic,unknown` | `.env` (CSV) — widened in PR 3 to admit Agitator traffic; further widened post-ADR-011 2026-06-07 amendment to admit propagation-gap signal |
| `DASHBOARD_INGEST_DRY_RUN` | `false` | `.env` (bool) |

`source` is set by the apps' request-logger middleware from the `X-Source`
header (default `unknown` — ADR-011 2026-06-07 amendment; React SPAs tag
`prod` explicitly in their fetch wrapper). The parser's `_infer_source`
precedence:
- `event=request` with path in `(/health, /api/health, /actuator/health)` → `source="health"` (beats explicit — path cannot be overridden by a header)
- Explicit `source=<value>` in the log line → honored
- Otherwise → `source="unknown"`

Allowed vocabulary: `prod` (React SPAs only), `synthetic` (Agitator, PR 3 ✅),
`test` (Playwright `extraHTTPHeaders`), `health` (parser-derived),
`unknown` (middleware default for missing-header / out-of-request events).

The default `(level ∈ {WARN, ERROR}) AND (source ∈ {prod, synthetic})` predicate keeps healthcheck heartbeat, INFO business events, and Playwright E2E traffic out of Chroma — sharp signal, ~$0 ongoing cost. Agitator traffic is admitted by default so a `docker compose up` + scenario click is enough to populate Chroma.

`DASHBOARD_INGEST_DRY_RUN=true` makes `upsert_entries` short-circuit before any embedder call — operator-safe preview of what the filter would pass without spending tokens. Backfill + watcher still log `parsed`, `passed_filter`, `embedded` so the filter behavior is visible.

Cost-saver gate: `upsert_entries` queries Chroma for existing IDs (`store._collection.get(ids=..., include=[])`) BEFORE the embedder is called. Content-hash IDs (`{app}:{sha1(raw)[:16]}`) make restarts against a populated Chroma volume cost $0.

---

## Agitator (PR 3 ✅)

Operator-driven load generator bundled into the dashboard (ADR-014).
Lives at `dashboard/src/log_dashboard/agitator/` + `routers/agitator.py` +
`dashboard/frontend/src/pages/LogGenerator.tsx`.

| Invariant | Why |
|---|---|
| Operator-button-only — never auto-fires | Cost determinism + demo flow |
| Every request tags `X-Source: synthetic` at a single seam (`http_client.build_client`) | One enforcement point so no scenario can drift |
| Scenarios are bounded — finite count AND finite duration | Caps cost; cancellation is `asyncio.Task.cancel()` |
| Global concurrent-run cap (`AGITATOR_MAX_CONCURRENT_RUNS=2`) | Keeps the dashboard process responsive |
| Same scenario cannot double-launch while a prior run is `running` | Prevents accidental hammering |
| Run state lives in-memory (`RunRegistry`, ring buffer of 50) | Restart clears history; durable signal lives in Chroma + log volumes |
| Agitator's own logs are INFO (`agitator_run_started` / `agitator_run_complete`) — dropped by ingest gate | Zero Chroma cost from the Agitator's own observability |
| `_sanitize_error` strips credential-shaped tokens before storing `last_error` | Defence-in-depth per the NEVER LOG CREDENTIALS rule |
| `sda-degraded` requires `ENABLE_CHAOS=true` — router returns 409 otherwise; UI greys the card | Chaos is a dev-only switch per ADR-013 |

Scenarios (10 total, one+ per app):
- **FNOL**: `auth-spike`, `payload-fuzz`, `policy-not-found`, `claim-burst`
- **SDA**: `sda-degraded` (slow chaos), `error-burst` (error:500 chaos)
- **Customer Portal**: `cp-read-burst`, `cp-degraded` (slow chaos)
- **Agent Portal**: `ap-read-burst`, `ap-degraded` (slow chaos)

Full scenario table + design notes in ADR-014.

`/api/status` gains a `corpus_empty: bool` flag (Chroma count == 0 with
the vectorstore wired up). The Overview UI shows a one-line banner with
a "Open Log Generator" link when true.

---

## LangGraph Agent (PR 4a ✅)

Phase 7e's first slice — `POST /api/chat` + AI Chat UI. ADR-015 captures
the design rationale.

| Invariant | Why |
|---|---|
| 5-node StateGraph named per `.claude/rules/dashboard.md:24`: ingest → analyze → correlate → predict → respond | Rule-driven naming + standard agent loop underneath |
| Tools: `query_logs` (Chroma) + `get_app_status` — DI'd via `build_tools(settings, vectorstore)` at compile time | No globals; tools degrade gracefully when `vectorstore=None` |
| `correlate` dispatches tools manually (not `langgraph.prebuilt.ToolNode`) | ToolNode needs LangGraph's internal runtime context; manual dispatch is ~20 lines + fully testable |
| Session memory: `langgraph.checkpoint.memory.InMemorySaver`, thread_id = `{jwt_sub}:{session_id}` | Matches RunRegistry's stateless-by-design stance; restart-lossy on purpose |
| `SessionIndex` LRU (default cap 200) evicts oldest via `adelete_thread` | Bounds in-process memory growth; eviction failures swallowed |
| `DASHBOARD_LLM_DRY_RUN=true` is the **default** (safe-by-default) | Cost-safety asymmetry — see ADR-015 §5 |
| Dry-run uses a custom `_DryRunChatModel` (subclass of `BaseChatModel`) that scripts: tool_call → ToolMessage → canned final answer | Exercises the FULL graph topology in tests without any network call |
| `analyze` + `predict` share `_invoke_llm_with_tools`; separate nodes only for the rule's 5-name palette | Single implementation, two graph slots, no duplicated logic |
| `POST /api/chat` defaults to non-streaming JSON; `streaming: true` returns SSE (PR 4b — see additions block below). Both paths run the same graph, so the response shape can't drift. | Additive contract; pre-flight errors (401 / 413 / 503) always return JSON |
| Cost caps (3): `LLM_MAX_TOOL_CALLS_PER_REQUEST=4`, `LLM_MAX_INPUT_TOKENS_PER_REQUEST=8000` (tiktoken `o200k_base`), `LLM_MAX_MESSAGES_PER_SESSION=40` | Deterministic in-graph bounds; no advisory middleware |
| Credential redaction in NEW `credentials.py` — `sanitize_user_input` + `sanitize_log_raw` cover Bearer/X-API-Key/password/JWT-shape/DSN | Defence-in-depth at BOTH input (router + ingest_node) AND output (tool `raw` field) |
| Shared shape detection in `credential_patterns.py` — JWT pattern + sensitive-keyword vocabulary; `credentials.py` and `agitator/runs.py::_sanitize_error` both import. Each keeps its own policy (surgical substitute vs. drop whole message). Landed in the 2026-06-07 dedup chore PR. | Single source of truth for what counts as "secret-shaped" — the two consumers can't drift |
| LangSmith metadata: every `ainvoke` carries `{session_id, jwt_sub, dry_run}` | Filterable in LangSmith UI |
| Proactive-loop background scan shipped in **PR 4c** ✅ — see the Proactive Scan block below | Closes Phase 7. |

### PR 4b additions

| Invariant | Why |
|---|---|
| `LogEntry.id` is `{app}:{sha1(raw)[:16]}` everywhere — parser + Chroma + frontend | One stable identifier so `/errors/:id` URLs survive across requests + restarts; matches the Chroma doc ID so `GET /api/errors/{id}` is a single O(1) `_collection.get` |
| `GET /api/errors/{id}` reuses the same compiled graph as `/api/chat` — synthesises a `HumanMessage` and invokes via `graph.ainvoke` | One code path; all 4a cost caps + redaction + dry-run + LangSmith metadata apply transparently. Ephemeral `session_id` per click, registered with `SessionIndex` so the LRU evicts it |
| `lookup_entry_by_id` + `metadata_to_log_entry` live in `ingest/vectorstore.py` (PR 4b moved the conversion helper there) | Search router (`Document` path) and errors router (`_collection.get` path) share one inverse-of-`make_metadata` function — cannot drift |
| `routers/chat.py` SSE path uses `graph.astream(stream_mode="updates")` + Starlette `StreamingResponse(media_type="text/event-stream")` + `X-Accel-Buffering: no` header. Frontend reads via `fetch` + `response.body.getReader()` (EventSource is GET-only) | No new server-side deps (no `sse-starlette`); no new client deps; per-node payloads are status snapshots, not full messages |
| Agent response adapters (`extract_answer`, `extract_citations`, `count_tokens`, `is_openai_api_error`) live in `agent/responses.py` and are shared by both routers | Single source of truth for output shape — JSON `ChatResponse`, SSE `complete` event, and `ErrorDetailResponse.analysis` all run through the same sanitisation + reshape |
| Defence-in-depth: errors route sanitises `entry.raw` BEFORE returning it AND before sending it to the LLM | A credential planted in a log line by an upstream-app bug never crosses into the response body OR the LangSmith trace |
| Every OpenAI Chroma upsert prints a per-app level-count summary table to stdout (with per-batch tokens + USD + cumulative session spend) + emits a structured `embedding_complete` log event carrying `batch_tokens` / `batch_cost_usd` / `session_tokens` / `session_cost_usd` | Operator-visible — answers "what did I just pay OpenAI to embed?" and "what have I spent since startup?" without parsing JSON. Cost is computed from tiktoken `cl100k_base` token count × `text-embedding-3-small` list price ($0.02 / 1M tokens). Skipped on dry-run and on full-dedup batches (no embed = no table). |
| `metadata_to_log_entry` round-trips `LogEntry.source` from Chroma metadata | Without this, Agitator-tagged `synthetic`, parser-derived `health`, and Playwright-tagged `test` (when admitted) all silently fall back to the historical `LogEntry.source = "prod"` default on read — destroying the provenance signal ADR-011's X-Source propagation works to preserve. PR 4b fix. (Post-ADR-011 2026-06-07 amendment, missing-source defaults to `unknown` at parse time, but the round-trip mechanism is what makes the labels durable.) |

---

## Proactive Scan (PR 4c ✅)

Phase 7e's final slice — closes Phase 7. Background loop in
`dashboard/src/log_dashboard/agent/proactive.py` + lifespan wiring +
findings ride on `/api/status`. ADR-016 captures the design rationale.

| Invariant | Why |
|---|---|
| Loop skips invocation entirely when `DASHBOARD_LLM_DRY_RUN=true` — logs `proactive_scan_skipped reason=llm_dry_run`. **Real scans require the opt-in chain: `DRY_RUN=false` AND `SCAN_ENABLED=true`.** | Cost-safety asymmetry from ADR-015 §5 extends to the background loop. Either flag alone is safe — dry-run lets you verify scheduling without paid spend. |
| Loop is opt-in via `DASHBOARD_PROACTIVE_SCAN_ENABLED=false` default; lifespan only schedules the task when true. `task.cancel()` on shutdown. | Asymmetric: forgotten env var → no loop, no spend. Mirrors the dry-run asymmetry. |
| Reuses the SAME compiled graph `app.state.agent_graph` that backs `/api/chat` + `GET /api/errors/{id}` | One code path; every PR 4a cost cap, credential redaction, dry-run, and LangSmith metadata tag applies transparently. |
| `_run_one_scan` synthesises a HumanMessage from `PROACTIVE_SCAN_PROMPT` (in `agent/proactive_prompt.py`) with `{lookback_minutes}` interpolated | Prompt held in its own module so the wording can evolve without churning `proactive.py`; testable in isolation. |
| Agent answers with `NO_ANOMALIES` sentinel for quiet scans → `_run_one_scan` returns `None`, buffer untouched | Sentinel keeps the buffer quiet during steady-state. Strip + startswith check tolerates trailing whitespace. |
| `jwt_sub = "system:proactive-scan"` (constant) on every scan invocation | Filterable in LangSmith without conflating with real admin chat sessions. |
| Findings stored in `FindingsBuffer` (`collections.deque(maxlen=50)`) on `app.state.findings_buffer` — restart-lossy by design | Same posture as Agitator's `RunRegistry`. Durable signal lives in Chroma + log volumes. Buffer is the running commentary. |
| Buffer is created unconditionally during lifespan (even when scan is off) | `/api/status` always serialises `proactive_findings: []` + `scan_enabled` without state-check branches. |
| `StatusResponse` gains 4 fields: `proactive_findings`, `scan_enabled`, `last_scan_at`, `next_scan_at` — all backwards-compatible defaults | No new endpoint. Findings poll piggybacks on the 15s status poll. Older frontends ignore the new fields and keep working. |
| Frontend `ProactiveFindingsPanel` renders nothing when scan is OFF AND no findings; renders an empty-state hint when scan is ON but quiet; renders findings inline (top-5 newest first) above the status grid | Keeps Overview clean for operators who haven't opted in; gives feedback the loop is alive when it is. |
| Citations deep-link via `<Link to={`/errors/${citation.id}`}>` to the PR 4b error-detail route | One end-to-end click from a finding to the agent's per-error analysis. |
| Severity is derived deterministically from the citation set (any ERROR → error, else any WARN → warn, else info) — NOT from the LLM | UI pill color is grounded in actual log levels, not the LLM's narrative tone. |
| Findings buffer growth bounded at `maxlen=50` even though `/api/status` only surfaces top-N (default 5) | Defence-in-depth — even a pathological scan rate cannot OOM the process. |
| Loop survives iteration failure: any exception during `_run_one_scan` is logged as `proactive_scan_iteration_failed` and the loop continues. Only `asyncio.CancelledError` propagates. | One bad scan must not stop the proactive surface from ever scanning again. |
| New Agitator scenario `error-burst` (requires `ENABLE_CHAOS=true`) sends `X-Chaos: error:500` against SDA `/policies` so operators can drive ERROR-tier signal into Chroma on demand | Mirrors `sda-degraded` structurally. The proactive scan needs ERROR-tier signal in Chroma; the chaos middleware level split (ADR-013 2026-06-06 amendment) makes that work end-to-end. |
| Chaos middleware (`apps/*/middleware/chaos.*`) splits `chaos_honored` log level by status class: `error:<5xx>` → ERROR, `error:<4xx>` → WARN, `slow:` and invalid stay WARN. Per ADR-013 2026-06-06 amendment. | Without ERROR-tier chaos signal in Chroma, the proactive scan is half-blind — `project_no_error_path_in_apps` documents why. |
| **Live-validated 2026-06-06** — chaos middleware level split confirmed per-app (SDA / FNOL / CP / AP); `corpus_empty` flipped to false within seconds of the first WARN traffic; embed-summary tables emitted as documented in `README.md`; 4 Playwright E2E suites green (135 passed / 0 failed) on the same stack. | Audit-trail breadcrumb that the design above actually ran end-to-end on the live stack, not just in unit tests. |

### Settings (defaults documented in `.env.example`)

| Env var | Default | Range |
|---|---|---|
| `DASHBOARD_PROACTIVE_SCAN_ENABLED` | `false` | bool |
| `DASHBOARD_PROACTIVE_SCAN_INTERVAL_SECONDS` | `900` (15 min) | 60..86400 |
| `DASHBOARD_PROACTIVE_SCAN_LOOKBACK_MINUTES` | `30` | 5..1440 |
| `DASHBOARD_PROACTIVE_SCAN_MAX_FINDINGS` | `5` | 1..20 |

---

## MCP Server Usage
See the MCP usage rule in `CLAUDE.md` — dashboard backend uses **docs-langchain**,
dashboard frontend uses **context7**.
