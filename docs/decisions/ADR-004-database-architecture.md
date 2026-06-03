# ADR-004: Database Architecture

**Status:** Superseded by [ADR-005](ADR-005-shared-data-api-as-sole-data-layer.md)

> Retained for project history. The current data-ownership model — Shared Data API as the sole writer/reader of both PostgreSQL and MongoDB — is documented in ADR-005 and `docs/tech/data-model.md`.

## Decisions
1. Shared Data API, FNOL, and Agent Portal share a single PostgreSQL instance.
2. Customer Portal uses MongoDB (Mongoose) instead of PostgreSQL.

## Rationale
A shared PostgreSQL instance simplifies local infrastructure. Each app uses its own tables within the shared `insurance` database — realistic for an insurance back-office context where apps share a common data tier.

MongoDB suits the Customer Portal's flexible, user-profile-centric data model. It also introduces a second database type, producing structurally different log patterns — MongoDB errors look different from PostgreSQL errors, which enriches the dashboard's analysis challenge.

## Consequences
Apps sharing PostgreSQL must not conflict on table names. Each creates its own tables on startup. Shared Data API is the authoritative source for customer and policy data.

FNOL owns the `claims` and `vehicles` tables. Agent Portal owns `adjusters` and `assignments` — it reads FNOL's `claims` table directly (same PostgreSQL instance, shared read) to drive its claim-handling workflows.

Customer Portal is fully isolated from the shared PostgreSQL instance. MongoDB runs in its own container with its own persistent volume.
