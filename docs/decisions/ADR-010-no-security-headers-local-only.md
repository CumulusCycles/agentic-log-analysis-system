# ADR-010: No Security Headers Middleware (Local-Only Deployment)

**Status:** Accepted

## Decision

The four supporting apps (Shared Data API, FNOL, Customer Portal, Agent Portal) and
the Phase 7 Agentic Log Analysis Dashboard do NOT install or configure security-header
middleware. Specifically:

- **Node/Express (Customer Portal):** no `helmet`, no `cors` (single-origin only).
- **Python/FastAPI (Shared Data API, FNOL, Dashboard backend):** no `SecureHeadersMiddleware`,
  no `CORSMiddleware`, no `TrustedHostMiddleware`.
- **Java/Spring Boot (Agent Portal):** no `spring-boot-starter-security`, no
  `SecurityFilterChain` bean, no default Spring Security response-header filter
  (HSTS, X-Content-Type-Options, X-Frame-Options, etc.).

JWT authentication, JSON body-size limits, and the per-app `X-API-Key` gate on the
Shared Data API remain in place — those are application-layer auth/quota controls,
not response-header hardening.

## Rationale

- **ADR-001** pins the entire deployment to a single developer machine running Docker
  Compose; no app port is reachable from outside `localhost`.
- **ADR-006** mandates JWT on every protected endpoint and per-app `X-API-Key` for
  caller attribution; the authentication threat surface is already covered.
- **No PII in any database** — seed data uses synthetic names and policy numbers.
- Security headers protect browsers from malicious responses (XSS, clickjacking,
  MITM downgrade). With no public network reach, no shared cookie domain, and a
  single-user development context, none of those threats are reachable.

Adding `helmet` / Spring Security / FastAPI middleware would introduce per-stack
configuration surface (CSP allow-lists, frame-ancestors policy, CORS preflight rules)
with zero risk reduction in the local-only context.

## Consequences

- The Phase 7 dashboard inherits this decision. If the dashboard is later exposed
  beyond `localhost` (a public-facing demo, a recorded screencast served from a
  CDN, a port-forward through a tunnel like ngrok), the headers MUST be backfilled
  in a single cross-cutting PR before that exposure. Recommended set:
  - HSTS (`Strict-Transport-Security: max-age=63072000; includeSubDomains`)
  - X-Content-Type-Options: nosniff
  - X-Frame-Options: DENY
  - Content-Security-Policy: per-app allow-list (template at backfill time)
  - Referrer-Policy: strict-origin-when-cross-origin
- The Customer Portal's Express app does NOT call `app.disable("x-powered-by")` for
  security reasons — it's already disabled to avoid the cosmetic `X-Powered-By: Express`
  header leak. That existing line stays.
- Tests do not assert the absence of security headers; if a future PR adds them,
  the absence assertion isn't a regression to fix.

## References

- ADR-001: Local Docker Compose only — no cloud, no public network reach
- ADR-006: Auth strategy — JWT + per-app `X-API-Key`
- Phase 6.5 best-practices pass — the work that prompted documenting this decision
