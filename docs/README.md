# Documentation Index

Read these docs before building. They define the decisions, architecture, and conventions
that all implementation must follow.

---

## Start Here

| File | What it covers |
|---|---|
| [`project-brief.md`](project-brief.md) | Narrative overview — what this system is, why it exists, and what the primary deliverable is |
| [`development-workflow.md`](development-workflow.md) | Hooks, slash commands, review flow, and phase checkpoints |

---

## Architecture

| File | What it covers |
|---|---|
| [`architecture/system-overview.md`](architecture/system-overview.md) | Container topology, data flow, volume layout, and how all eight services fit together |

---

## Tech

| File | What it covers |
|---|---|
| [`tech/tech-stack.md`](tech/tech-stack.md) | Per-app language, framework, database, and tooling choices |
| [`tech/logging-strategy.md`](tech/logging-strategy.md) | Per-stack log formats, volume mount paths, and dashboard ingestion approach |
| [`tech/data-model.md`](tech/data-model.md) | Mongo + Postgres schemas, claim status enum, seed counts |
| [`tech/file-naming-convention.md`](tech/file-naming-convention.md) | File and path naming rules for the whole repo |

---

## Architecture Decision Records

| File | Decision |
|---|---|
| [`decisions/ADR-001-local-docker-only.md`](decisions/ADR-001-local-docker-only.md) | All infrastructure runs locally via Docker Compose — no cloud deployment |
| [`decisions/ADR-002-monorepo.md`](decisions/ADR-002-monorepo.md) | All apps in a single repo, orchestrated from one `docker-compose.yml` |
| [`decisions/ADR-003-logging-strategy.md`](decisions/ADR-003-logging-strategy.md) | Polyglot logging — each app uses its native format, dashboard handles heterogeneity |
| [`decisions/ADR-004-database-architecture.md`](decisions/ADR-004-database-architecture.md) | _Superseded by ADR-005._ Original DB topology (shared Postgres, dedicated Mongo) |
| [`decisions/ADR-005-shared-data-api-as-sole-data-layer.md`](decisions/ADR-005-shared-data-api-as-sole-data-layer.md) | Shared Data API owns both DBs — FNOL/CP/AP access data only via HTTP |
| [`decisions/ADR-006-auth-strategy.md`](decisions/ADR-006-auth-strategy.md) | JWT for insurance apps via SDA; standalone JWT for Dashboard; per-app API keys |
| [`decisions/ADR-007-background-claim-status-simulator.md`](decisions/ADR-007-background-claim-status-simulator.md) | In-process simulator inside SDA advances claim statuses for log realism |
| [`decisions/ADR-008-defer-alembic-to-post-phase-3.md`](decisions/ADR-008-defer-alembic-to-post-phase-3.md) | Phase 3 uses `create_all`; Alembic lands as a dedicated PR before Phase 4 |
