# ADR-011: X-Source Header Convention

**Status:** Accepted (amended 2026-06-07 — see Amendments below)

## Decisions
1. Each of the four logging apps (Shared Data API, FNOL, Customer Portal, Agent Portal) reads an optional `X-Source: <value>` HTTP header from incoming requests in its request-logger middleware and emits a `source=<value>` field in the per-request log line.
2. When the header is absent, apps default to `source=prod`. Apps do **not** validate the value — they trust the edge.
3. The dashboard parser's `_infer_source` derives `source=health` for healthcheck request paths **before** consulting the explicit field; the header cannot override a healthcheck request. For all other events, explicit beats default.
4. Allowed vocabulary: `prod`, `synthetic`, `test`, `health`. The dashboard's ingest gate (`DASHBOARD_INGEST_SOURCES`) is the single enforcement point — unknown values are simply not in the allow-list and get dropped.
5. Each frontend's `playwright.config.ts` sets `use.extraHTTPHeaders: { "X-Source": "test" }` so every E2E request carries the test tag and is excluded from Chroma by default.

## Vocabulary

| Value       | Set by                                                | In default `DASHBOARD_INGEST_SOURCES`? |
|-------------|-------------------------------------------------------|----------------------------------------|
| `prod`      | Header absent (app default)                           | YES                                    |
| `synthetic` | Agitator (PR 3 of the agitator sequence)              | NO today — added by PR 3               |
| `test`      | Playwright `extraHTTPHeaders` in each frontend config | NO                                     |
| `health`    | Parser-derived from healthcheck path                  | NO                                     |

## Rationale
The dashboard's 7d ingest gate filters log lines on `source` before any embedding call. Without per-line tagging at the app layer, every Playwright E2E run leaks dozens of log lines into the embedding pipeline as signal noise. (Phase 7 also paid OpenAI embedding cost on each leak; Phase 8 / [ADR-017](ADR-017-local-ai-via-ollama.md) swapped embeddings to local Ollama so the residual concern is signal quality alone.) Reading one header in each app's existing request-logger middleware is a one-line edit per stack; no new middleware file is needed.

Trust-the-edge keeps the convention from drifting across four apps. The dashboard parser is the single normalization point (`.strip().lower()`), and the ingest gate is the single enforcement point. Adding allow-list validation in four apps would mean four places to keep in sync for zero added safety in a local-only deployment (see ADR-001).

Healthcheck-path detection moves to the front of the parser's precedence chain because path is an immutable property of the request that no caller-supplied header should override. Without that reorder, the new app-side `source=prod` default would suppress the parser's existing `source=health` derivation and heartbeat would leak into Chroma — a strict regression of 7d's gate.

## Consequences
- E2E runs no longer pollute Chroma (~$0 incremental from Playwright traffic).
- The Agitator (PR 3 of the agitator sequence) will set `X-Source: synthetic` and the default `DASHBOARD_INGEST_SOURCES` will widen to `prod,synthetic` to admit those lines.
- All four apps' per-request log line gains a `source=<value>` field; the dashboard parser already had the slot.
- The 7d parser test suite continues to pass unchanged because the only existing explicit-source test uses a non-`request` event (path detection doesn't fire).
- Inter-service propagation through the SDA clients (FNOL/CP/AP → SDA) **landed in the PR 4a Phase 7e ship (2026-06-05)** — the deferred design from above. Each language got its native carrier: `structlog.contextvars` in Python (SDA/FNOL), `AsyncLocalStorage` in Node (CP), SLF4J `MDC` in Java (AP). Each app's request middleware binds the inbound `X-Source` onto the carrier at dispatch entry and clears it at exit (so prior-request state can't leak); each outbound HTTP client reads the carrier and forwards `X-Source` as a per-call header. Effect: SDA's WARN/ERROR domain events now carry the originating source. Before: ~100% of Chroma WARN entries showed `source=prod` regardless of real origin. After: synthetic-driven runs surface as `source=synthetic` in the corpus.
- Domain events emitted OUTSIDE a request context (startup, background tasks, scheduled work) have no contextvar/ALS/MDC bound; the parser tags them `source=unknown` rather than silently defaulting to `prod` so the operator can spot propagation gaps in the dashboard UI. `DASHBOARD_INGEST_SOURCES` default widens to `prod,synthetic,unknown` to admit the leak-detection signal through the gate. Should approach zero entries once the per-app coverage is rock-solid.

## References
- `.claude/rules/dashboard.md` — Phase 7d ingest gate (`DASHBOARD_INGEST_LEVELS × DASHBOARD_INGEST_SOURCES × DASHBOARD_INGEST_DRY_RUN`)
- `.claude/rules/logging.md` — per-app log field contract
- `dashboard/src/log_dashboard/ingest/parsers.py` — `_infer_source`
- `dashboard/src/log_dashboard/schemas.py` — `LogEntry.source`
- ADR-001 — local-only threat model (no allow-list validation needed at the edge)
- ADR-006 — sibling `X-API-Key` convention

---

## Amendment — 2026-06-07: `prod` means real UX traffic only

### Change

1. **Middleware default flips `prod` → `unknown`** in all four apps' request-logger middleware (SDA, FNOL, CP, AP). When the inbound request has no `X-Source` header, the middleware now tags the log line `source=unknown` instead of `source=prod`.
2. **React SPAs explicitly tag `X-Source: prod`** at a single seam — each SPA's `request()` fetch wrapper sets the header on every outbound call. Mirrors the Agitator's `build_client` single-seam pattern.

### Why

PR #41's Vectorstore Stats tab made the prior semantic visible: 95 entries were tagged `source=prod` in Chroma despite the operator never having clicked through any React SPA. The original convention treated "header absent" as "real-user default" — so ad-hoc curls, internal background calls, and anything else lacking the header silently landed in the `prod` bucket. Any future analytics, anomaly detection, or "is this app being used" intuition built off `by_source.prod` was therefore polluted.

The corrected rule: **`prod` means "an authenticated user took an action through a React SPA in the browser."** Nothing else lands in `prod`. Missing-header inbound traffic is the leak-detection signal (`unknown`), surfacing propagation gaps the operator can investigate.

### Vocabulary update

| Value       | Set by                                                | In default `DASHBOARD_INGEST_SOURCES`? |
|-------------|-------------------------------------------------------|----------------------------------------|
| `prod`      | **React SPA fetch wrapper (explicit `X-Source: prod`)** | YES                                  |
| `synthetic` | Agitator (PR 3 of the agitator sequence)              | YES                                    |
| `test`      | Playwright `extraHTTPHeaders` in each frontend config | NO                                     |
| `health`    | Parser-derived from healthcheck path                  | NO                                     |
| `unknown`   | **Middleware default when header is absent**          | YES                                    |

The Playwright `extraHTTPHeaders` override (`X-Source: test`) wins over the SPA wrapper's default header because Playwright sets it at the browser-context layer, before the wrapper runs. E2E traffic stays correctly tagged `test`.

### Migration

The ~95 stale `prod` entries already in Chroma are not migrated — the dedup gate won't re-embed them, and real `prod` from the fix dilutes them over time. Operator decision; documented for transparency.

### Files changed in the amendment

- `apps/shared-data-api/src/shared_data_api/middleware/request_logger.py` — `_normalize_source` default
- `apps/fnol/src/fnol/middleware/request_logger.py` — `_normalize_source` default
- `apps/fnol/src/fnol/clients/shared_data_api.py` — `_current_source` outbound fallback
- `apps/customer-portal/src/source-context.ts` — `normalizeSource` + `getCurrentSource`
- `apps/agent-portal/src/main/java/com/cumuluscycles/agentportal/logging/SourceContext.java` — `DEFAULT` constant
- `apps/{fnol,customer-portal,agent-portal}/frontend/src/lib/api.ts` — explicit `X-Source: prod`
- Test suites in all four apps + new `api.test.ts` per SPA frontend
- `.claude/rules/{logging,dashboard,apps}.md` — synchronised wording
