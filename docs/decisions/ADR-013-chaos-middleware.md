# ADR-013: Chaos Middleware (X-Chaos Header, ENABLE_CHAOS Gate)

**Status:** Accepted

## Decisions

1. Each of the four monitored apps (Shared Data API, FNOL, Customer Portal, Agent Portal) gains a thin chaos middleware that reads an `X-Chaos: <directive>` HTTP header and simulates the requested failure. The Agentic Log Analysis Dashboard does **not** get chaos middleware — it is the observer of the system, not a target.
2. The middleware is **gated by `ENABLE_CHAOS` env var**, default `false`. When `false`, the middleware short-circuits to a no-op regardless of the header (production-safe by default).
3. The directive vocabulary is deliberately small — two primitives that compose:
   - `slow:<ms>` — sleep `<ms>` (clamped to `0..60000`), then continue to the handler normally. Produces slow-call cascades downstream.
   - `error:<status>` — return immediate JSON `{"detail": "chaos"}` with HTTP `<status>` (`400..599`). Skips the handler entirely.
4. Malformed or out-of-range directives are rejected with HTTP `400` and a `chaos_directive_invalid` WARN log. Honored directives emit a `chaos_honored` WARN log on every fire.
5. Chaos events log at **WARN** so they pass the dashboard's 7d ingest filter (`DASHBOARD_INGEST_LEVELS=WARN,ERROR`) into Chroma. The PR 4 LangGraph agent needs to see induced chaos events to recognize cross-app cascades.
6. Stack position per app:
   - **SDA:** added BEFORE the API-key middleware (so the API-key check wraps chaos, i.e. chaos runs AFTER auth). Unauthenticated requests with `X-Chaos` are rejected by the API-key 401 before chaos sees them.
   - **FNOL / CP:** added immediately after the request-logger middleware. JWT is a route-level dependency, so chaos and JWT execute in the same dispatch path; chaos cannot bypass JWT route protection because chaos runs inside the dispatcher but routes still apply their own auth.
   - **AP:** `FilterRegistrationBean` at `setOrder(20)` (after JWT at 1 and request-logging at 10). Scoped to `/api/*` only so `/actuator/health` is never chaosed — the Docker healthcheck stays honest under any chaos config.

## Vocabulary

| Directive form | Behavior | Range |
|---|---|---|
| `slow:<ms>` | Sleep N ms, then forward to handler | `0..60000` |
| `error:<status>` | Immediate response with HTTP status + `{"detail":"chaos"}` | `400..599` |

Anything else — unknown verb, missing colon, non-numeric value, out-of-range value — is malformed.

## Rationale

**Why two primitives.** The starter scenario pack for PR 3 (Agitator) needs `slow` (for `sda-degraded` cross-app cascades) and `error` (for synthetic upstream failures). Adding more directives now — `db-timeout`, `random:<p>`, `connection-reset` — is speculative; we can extend after PR 3's scenarios reveal what's actually missing.

**Why ENV-gated default-off.** Production posture: never simulate failures unless explicitly enabled. The env-gate is the single safety switch; the middleware itself does not need additional safeguards. Operators flip `ENABLE_CHAOS=true` in the local stack's `.env` when running PR 3's Agitator scenarios.

**Why log at WARN.** Three reasons: (a) chaos is simulated *abnormal* behavior; WARN matches the semantic; (b) WARN passes the dashboard's existing 7d ingest filter into Chroma — INFO would not, and the LangGraph agent in PR 4 needs to see chaos events to recognize induced cascades; (c) WARN is loud enough to surface during E2E sweeps without polluting the production-shaped corpus.

**Why ChaosFilter runs AFTER auth on AP/SDA.** Chaos must not bypass security. If chaos could fire before auth, an unauthenticated attacker could induce 500-class failures across the system. Placing chaos inside the auth boundary (SDA: behind APIKeyMiddleware; AP: filter order > JWT filter order) keeps the security perimeter intact.

**Why the dashboard is skipped.** The dashboard is the system's diagnostic tool. Chaos in the dashboard's request handling would degrade its ability to *observe* chaos in the four monitored apps — exactly when the operator needs it most. The Agitator (PR 3) is the *source* of chaos directives; the dashboard's HTTP client sets `X-Chaos`, the apps' middlewares honor them.

**Why `/actuator/health` is excluded in AP only.** AP's filter binding is per-URL-pattern (`addUrlPatterns("/api/*")`), so excluding `/actuator/*` is a single config line. For SDA/FNOL/CP the equivalent guard is structural: the Docker healthcheck does not send `X-Chaos`, so healthchecks pass through chaos middleware untouched. No `/health` path-exclusion code is needed in any app.

## Consequences

- **`.env.example` gains `ENABLE_CHAOS=false`.** Operators copy to `.env` and flip when needed.
- **8 new log event entries** (4 apps × 2 events: `chaos_honored` + `chaos_directive_invalid`) in `docs/tech/log-events.md`.
- **No new test files in the dashboard** — only the 4 apps get tests for their chaos middleware.
- **Cross-app symmetry** — same directive grammar, same clamp bounds, same response shape, same log event names across Python (SDA/FNOL), Node (CP), and Java (AP). The parser-side normalization the dashboard does for other events does not need to differ for chaos.
- **AP requires `app.chaos.enabled: ${ENABLE_CHAOS:false}` in `application.yml`.** Both production and test resources bind the same default.
- **Per `feedback_no_paid_api_calls_without_confirmation`:** the chaos middleware itself does not call any external API. Activating chaos in the live stack does not change OpenAI cost — the dashboard's ingest filter still only embeds WARN/ERROR/source=prod, and chaos events match that filter shape.

## Stack-position diagrams

### SDA (FastAPI middleware, LIFO)
```
Request -> RequestLoggerMiddleware -> APIKeyMiddleware -> ChaosMiddleware -> handler
```
Auth fails first if X-API-Key is missing or invalid. Chaos runs AFTER auth resolved successfully.

### FNOL (FastAPI middleware, LIFO)
```
Request -> RequestLoggerMiddleware -> ChaosMiddleware -> handler (JWT dep)
```
Chaos can fire on any path. JWT decoding is a route-level dependency that runs inside the handler chain — slow:N delays the dependency, error:N short-circuits before the dependency runs.

### Customer Portal (Express middleware, FIFO)
```
Request -> requestLogger -> chaos -> routes (with requireAuth selectively)
```
Same shape as FNOL.

### Agent Portal (Spring Filter chain, by order)
```
Request -> JwtAuthenticationFilter (order=1, /api/*)
        -> RequestLoggingFilter (order=10, /api/* + /actuator/*)
        -> ChaosFilter (order=20, /api/*)
        -> handler
```
`/actuator/*` skips ChaosFilter entirely. JWT auth fails first if the bearer is missing or invalid.

## References

- [`.claude/rules/apps.md`](../../.claude/rules/apps.md) — per-app middleware/filter conventions
- [`docs/tech/log-events.md`](../tech/log-events.md) — `chaos_honored` and `chaos_directive_invalid` event entries
- ADR-011 — `X-Source` header convention (sibling cross-app header)
- `project_agitator_design` memory — Agitator PR 3 scenario pack (uses chaos for `sda-degraded`)
- `feedback_never_log_credentials` — chaos events do NOT include any credential value (no Authorization header, no API key)
