# ADR-005: Shared Data API as the Sole Data-Access Layer

**Status:** Accepted (supersedes ADR-004)

## Decisions
1. The Shared Data API owns both databases — PostgreSQL (`claims`, `claim_status_history`) and MongoDB (`users`, `policies` with embedded vehicles).
2. FNOL, Customer Portal, and Agent Portal access all domain data over HTTP through the Shared Data API. They have no direct database driver or connection.
3. FNOL is the sole write path. Customer Portal and Agent Portal are strictly read-only.
4. The Agentic Log Analysis Dashboard does not consume the Shared Data API — it operates only on log volumes.

## Rationale
The previous design (ADR-004) had FNOL as the only HTTP client of the API while Customer Portal owned its own Mongo and Agent Portal read FNOL's Postgres tables directly. A "shared" API with one real consumer is not shared, and the divergent integration styles meant a claim created in FNOL would never appear in Customer Portal. Centralizing through the Shared Data API makes the API genuinely shared, gives the system a single source of truth, and produces a richer, attributable log stream — every Shared Data API request can record `caller=<app>` and `user=<id>`, which is the primary log source the dashboard correlates against.

Making CP and AP read-only is a deliberate scope choice. The project's purpose is generating realistic logs, not building working insurance products. Read-only views with seeded data and auth flows generate ample log activity without the cost of full CRUD.

## Consequences
- Customer Portal drops its Mongoose dependency. Agent Portal drops Spring Data JPA. Both become HTTP clients of the Shared Data API.
- A new 7th log volume `shared-data-api-logs` is introduced. See `.claude/rules/infrastructure.md` and `docs/tech/logging-strategy.md`.
- With CP/AP read-only and FNOL only creating claims, claim statuses would never transition. ADR-007 introduces a background simulator inside the Shared Data API to advance statuses and keep CP/AP logs dynamic.
- Inter-service auth is required so the Shared Data API can attribute every request to a calling app. See ADR-006.
- Schemas, status enum, and seed counts are documented in `docs/tech/data-model.md`.
