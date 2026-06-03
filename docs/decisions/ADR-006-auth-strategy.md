# ADR-006: Authentication Strategy

**Status:** Accepted

## Decisions
1. All four apps require login. There is no registration UI — users and credentials are pre-seeded by the Shared Data API on startup, and documented in `.env.example`.
2. FNOL, Customer Portal, and Agent Portal authenticate end users via JWT (HS256, shared `JWT_SECRET`) issued by the Shared Data API at `POST /auth/login`.
3. The Agentic Log Analysis Dashboard uses a separate, standalone JWT (`DASHBOARD_JWT_SECRET`) with env-supplied admin credentials. It does not depend on the Shared Data API to authenticate.
4. Every call between an app and the Shared Data API includes an `X-API-Key` header identifying the caller. Keys are per-app (`SHARED_DATA_API_KEY_FNOL`, `_CUSTOMER_PORTAL`, `_AGENT_PORTAL`), checked in middleware, and logged on every request as `caller=<app>`.

## Rationale
A single `JWT_SECRET` issued by the Shared Data API gives the three insurance apps one source of user identity. HS256 with a shared secret is sufficient for a local Docker stack — asymmetric keys add no value here.

The Dashboard is split off intentionally. Its job is to remain operational when the insurance apps are sick; if its auth depended on the Shared Data API being healthy, the dashboard would be unavailable exactly when it is most needed. Local env-based admin credentials keep it self-contained.

Per-app API keys give the Shared Data API a reliable caller identity independent of the user JWT. That attribution is what makes the Shared Data API log stream the dashboard's richest data source — `caller=<app> user=<id> METHOD /path → status in Xms` answers correlation questions without log-join gymnastics.

Login-only (no registration, no password reset) is a deliberate scope cap. Form validation, email verification, and reset flows would add 2–3 days for zero project value — none of these apps are real signup products.

## Consequences
- JWT claims: `{ user_id, role, app, exp }`. Roles are `customer`, `agent`, `admin`. Access tokens are short-lived (60 min). No refresh tokens.
- Demo credentials live in `.env.example`: customers (5), agents (5), and one `Admin/Admin` dashboard login.
- The Shared Data API logs every inbound request with caller and user attribution to its log volume `shared-data-api-logs`. See ADR-005 and `.claude/rules/logging.md`.
- Library choices are documented in `docs/tech/tech-stack.md` (`PyJWT`, `jsonwebtoken`, `jjwt`, `bcrypt`/`bcryptjs`/`BCryptPasswordEncoder`).
