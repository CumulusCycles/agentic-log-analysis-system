# ADR-004: Database Architecture

**Status:** Superseded by [ADR-005](ADR-005-shared-data-api-as-sole-data-layer.md)

> **Original decision (now superseded):** Shared Data API, FNOL, and Agent Portal would share a single PostgreSQL instance; Customer Portal would use MongoDB via Mongoose. Each app owned its own tables/collections and accessed the DBs directly.
>
> **What replaced it:** [ADR-005](ADR-005-shared-data-api-as-sole-data-layer.md) collapsed all four logging apps onto the Shared Data API as the sole data-access layer. SDA owns both PostgreSQL and MongoDB. FNOL / Customer Portal / Agent Portal call SDA over HTTP and carry no DB driver of their own. Customer Portal and Agent Portal are read-only by design; FNOL is the sole write path. The current data-ownership model and full schemas are documented in ADR-005 and [`docs/tech/data-model.md`](../tech/data-model.md).
>
> Retained for project history.
