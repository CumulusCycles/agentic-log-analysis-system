# ADR-008: Defer Alembic to a Post-Phase-3 PR

**Status:** Accepted — follow-up shipped (Alembic Baseline merged in PR #6, between Phase 3 and Phase 4)

## Decisions
1. The Shared Data API does not use Alembic in Phase 3. Schema is created on startup via `Base.metadata.create_all()`.
2. Schema changes in Phase 3 (CHECK constraints, indexes, new columns) are applied by wiping the `postgres-data` volume and letting the next boot recreate tables. This is acceptable because no real data exists yet to migrate.
3. Alembic will land in a dedicated PR after Phase 3 merges, before Phase 4 (FNOL) work starts. That PR will (a) add Alembic, (b) generate the initial baseline migration from the current models, (c) swap `create_all()` for `command.upgrade(...)` in the lifespan, and (d) document the dev workflow for new migrations.

## Rationale
Phase 3 ships a brand-new service with no installed base. Every schema change can safely "wipe and recreate" without losing user-visible state — seeds run on every fresh boot and produce identical data. Adding Alembic in Phase 3 would have meant maintaining migration files in parallel with rapidly-iterating models, with no actual data to migrate.

Once FNOL goes live in Phase 4 it begins writing real `claims` rows that survive across restarts. From that point on, schema evolution must preserve data — which is what Alembic exists to do. Doing the Alembic baseline as the last act of Phase 3 (or the first act of Phase 4 setup) lands it at exactly the right point in the timeline: schema is stable enough to baseline, real data hasn't accumulated yet, and there is no installed migration history to reconcile.

We surfaced this question now (rather than discovering it during Phase 4) because Phase 3's CHECK constraints and unique indexes required volume wipes during development — visible friction that would have compounded silently in Phase 4 if left unaddressed.

## Consequences
- During Phase 3 development, schema changes require `docker compose down` followed by `docker volume rm agentic-log-analysis-system_postgres-data agentic-log-analysis-system_mongodb-data agentic-log-analysis-system_shared-data-api-logs` and a fresh `docker compose up -d`. This is documented in `docs/tech/data-model.md`.
- After Phase 3 merges, the next PR introduces Alembic. The lifespan changes from `await postgres.create_all()` to `await postgres.run_migrations()`. Tests continue to use SQLite + `Base.metadata.create_all()` directly (Alembic is bypassed in tests for speed).
- Mongo schema "migrations" are handled by `ensure_indexes()` calling `create_index` which is idempotent. No migration framework needed on the Mongo side because the document model evolves additively.
- Subsequent ADRs may reference this one when describing schema changes that would otherwise require Alembic to be in place.

## Amendment — Alembic Baseline Shipped (PR #6)

The follow-up PR called out in Decision 3 has landed. Effective changes:

- Alembic is wired into the Shared Data API. Baseline migration was generated from the Phase 3 models (two tables, CHECK constraints, JSONB/BigInteger variants, FK, PK).
- The lifespan now calls `postgres.run_migrations()` (5-retry / 2s-backoff, `asyncio.to_thread`) instead of `Base.metadata.create_all()`. The `alembic_version` table is populated on startup.
- Tests continue to use SQLite + `Base.metadata.create_all()` directly via an autouse `_bypass_run_migrations` fixture in `tests/conftest.py` (with an opt-out marker for the three retry-test cases).
- The dev workflow for schema changes is now `alembic revision --autogenerate -m "<msg>"` instead of "wipe `postgres-data` and reseed." Decision 2's volume-wipe runbook is **no longer current** — it describes Phase 3's pre-Alembic posture and is retained only for historical context.

Authoritative dev workflow lives in `docs/tech/data-model.md` §Schema evolution. The `.claude/rules/apps.md` schema-enforcement line was updated in the same PR.
