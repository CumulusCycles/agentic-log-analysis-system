# Architecture Decision Records (ADRs)

Numbered records of the architectural decisions taken during this project's
build. Each ADR captures the decision, the rationale, and the consequences
that followed.

## Conventions

**File names:** `ADR-NNN-kebab-slug.md` (zero-padded three-digit number, lowercase kebab-case slug). See [`../tech/file-naming-convention.md`](../tech/file-naming-convention.md).

**Status field** (appears at the top of every ADR):

| Value | Meaning |
|---|---|
| `Accepted` | The decision is current and authoritative |
| `Accepted (amended …)` | Decision is current, but a later amendment refined it. The amendment block lives at the bottom of the same file |
| `Superseded by ADR-NNN` | A later ADR replaces this one. The body may be trimmed to a one-paragraph summary; the superseding ADR is the authority |

**Supersession is bidirectional.** When ADR-Y supersedes ADR-X, both files
carry the link — ADR-X's header points forward to Y, ADR-Y's header points
back to X. This is the audit trail.

**Amendments stay in-file.** When a decision evolves but is not fully
replaced, an `## Amendment — <date>` section is appended to the original
ADR rather than spawning a new one. Examples: ADR-003 (logging-strategy
amendment for SDA log volume), ADR-011 (X-Source default → `unknown`),
ADR-013 (chaos `chaos_honored` level split by status class).

## Index

| ADR | Status | Decision |
|---|---|---|
| [ADR-001](ADR-001-local-docker-only.md) | Accepted | All infrastructure runs locally via Docker Compose — no cloud deployment |
| [ADR-002](ADR-002-monorepo.md) | Accepted | All apps in a single repo, orchestrated from one `docker-compose.yml` |
| [ADR-003](ADR-003-logging-strategy.md) | Accepted (amended) | Polyglot logging — each app uses its native format, dashboard handles heterogeneity. Amended to add SDA as a log-volume writer |
| [ADR-004](ADR-004-database-architecture.md) | Superseded by ADR-005 | Original DB topology (shared Postgres + Mongoose-on-CP) — body trimmed |
| [ADR-005](ADR-005-shared-data-api-as-sole-data-layer.md) | Accepted | Shared Data API owns both DBs — FNOL/CP/AP access data only via HTTP |
| [ADR-006](ADR-006-auth-strategy.md) | Accepted | JWT for insurance apps via SDA; standalone JWT for Dashboard; per-app API keys |
| [ADR-007](ADR-007-background-claim-status-simulator.md) | Accepted | In-process simulator inside SDA advances claim statuses for log realism |
| [ADR-008](ADR-008-defer-alembic-to-post-phase-3.md) | Accepted (follow-up shipped) | Phase 3 used `create_all`; Alembic landed in PR #6 between Phase 3 and Phase 4 |
| [ADR-009](ADR-009-github-actions-ci.md) | Superseded by ADR-012 | Original per-app GitHub Actions workflow files with per-app README badges — body trimmed |
| [ADR-010](ADR-010-no-security-headers-local-only.md) | Accepted | No security-header middleware (helmet / Spring Security defaults / FastAPI middleware) — local-only threat model |
| [ADR-011](ADR-011-x-source-header-convention.md) | Accepted (amended 2026-06-07) | `X-Source` HTTP header for log-line attribution — vocab `prod`/`synthetic`/`test`/`health`/`unknown`; React SPAs tag `prod` explicitly |
| [ADR-012](ADR-012-consolidate-ci-workflows.md) | Accepted | Single `ci.yml` with `dorny/paths-filter@v3` conditional per-app jobs — supersedes ADR-009 |
| [ADR-013](ADR-013-chaos-middleware.md) | Accepted (amended 2026-06-06) | `X-Chaos: slow:<ms>` / `error:<status>` failure simulator on SDA/FNOL/CP/AP gated by `ENABLE_CHAOS`. `chaos_honored` level varies by status (5xx → ERROR) |
| [ADR-014](ADR-014-agitator-bundled-into-dashboard.md) | Accepted | Agitator load generator bundled into dashboard — operator-button-only bounded scenarios, `X-Source: synthetic` |
| [ADR-015](ADR-015-langgraph-agent.md) | Accepted | LangGraph agent for the AI Chat slice (Phase 7e PR 4a) — 5-node StateGraph, safe-by-default dry-run, credential redaction |
| [ADR-016](ADR-016-proactive-scan.md) | Accepted | Background proactive scan loop (Phase 7e PR 4c) — closes Phase 7. Opt-in chain (`DRY_RUN=false` AND `SCAN_ENABLED=true`) |

## Reading order for newcomers

To understand the system as it stands today, read in this order: **001 → 002 → 005 → 006 → 003 → 010 → 011 → 012 → 013 → 014 → 015 → 016**. ADRs 004, 007, 008, 009 are historical context (superseded or follow-up-complete).
