# ADR-011: X-Source Header Convention

**Status:** Accepted

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
The dashboard's 7d ingest gate filters log lines on `source` before any OpenAI embedding call. Without per-line tagging at the app layer, every Playwright E2E run leaks dozens of log lines into the embedding pipeline — both a cost surface and signal noise. Reading one header in each app's existing request-logger middleware is a one-line edit per stack; no new middleware file is needed.

Trust-the-edge keeps the convention from drifting across four apps. The dashboard parser is the single normalization point (`.strip().lower()`), and the ingest gate is the single enforcement point. Adding allow-list validation in four apps would mean four places to keep in sync for zero added safety in a local-only deployment (see ADR-001).

Healthcheck-path detection moves to the front of the parser's precedence chain because path is an immutable property of the request that no caller-supplied header should override. Without that reorder, the new app-side `source=prod` default would suppress the parser's existing `source=health` derivation and heartbeat would leak into Chroma — a strict regression of 7d's gate.

## Consequences
- E2E runs no longer pollute Chroma (~$0 incremental from Playwright traffic).
- The Agitator (PR 3 of the agitator sequence) will set `X-Source: synthetic` and the default `DASHBOARD_INGEST_SOURCES` will widen to `prod,synthetic` to admit those lines.
- All four apps' per-request log line gains a `source=<value>` field; the dashboard parser already had the slot.
- The 7d parser test suite continues to pass unchanged because the only existing explicit-source test uses a non-`request` event (path detection doesn't fire).
- Inter-service propagation through the SDA clients (FNOL/CP/AP → SDA) is **deferred**. Each SDA client (`apps/fnol/src/fnol/clients/shared_data_api.py`, `apps/customer-portal/src/clients/sda-client.ts`, `apps/agent-portal/src/main/java/com/cumuluscycles/agentportal/config/SdaClientConfig.java`) sets `X-API-Key` once at construction; per-call header threading needs its own design choice per language (contextvar in Python, AsyncLocalStorage in Node, Spring `RequestContextHolder` in Java). Effect today: ~5 SDA log lines per Playwright E2E run still tag `prod` because they travel through FNOL/CP/AP's pre-built SDA client. Below the corpus noise floor of ~21K lines; revisit if measurable.

## References
- `.claude/rules/dashboard.md` — Phase 7d ingest gate (`DASHBOARD_INGEST_LEVELS × DASHBOARD_INGEST_SOURCES × DASHBOARD_INGEST_DRY_RUN`)
- `.claude/rules/logging.md` — per-app log field contract
- `dashboard/src/log_dashboard/ingest/parsers.py` — `_infer_source`
- `dashboard/src/log_dashboard/schemas.py` — `LogEntry.source`
- ADR-001 — local-only threat model (no allow-list validation needed at the edge)
- ADR-006 — sibling `X-API-Key` convention
