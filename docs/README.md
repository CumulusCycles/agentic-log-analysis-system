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
| [`tech/file-naming-convention.md`](tech/file-naming-convention.md) | File and path naming rules for the whole repo |

---

## Architecture Decision Records

| File | Decision |
|---|---|
| [`decisions/ADR-001-local-docker-only.md`](decisions/ADR-001-local-docker-only.md) | All infrastructure runs locally via Docker Compose — no cloud deployment |
| [`decisions/ADR-002-monorepo.md`](decisions/ADR-002-monorepo.md) | All apps in a single repo, orchestrated from one `docker-compose.yml` |
| [`decisions/ADR-003-logging-strategy.md`](decisions/ADR-003-logging-strategy.md) | Polyglot logging — each app uses its native format, dashboard handles heterogeneity |
| [`decisions/ADR-004-database-architecture.md`](decisions/ADR-004-database-architecture.md) | Shared PostgreSQL for relational apps, dedicated MongoDB for Customer Portal |
