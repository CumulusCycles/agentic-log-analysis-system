# ADR-002: Monorepo

**Status:** Accepted

## Decision
Use a single repository with one root `docker-compose.yml`.

## Rationale
Cross-app concerns (volumes, networking, env vars) are easier to manage from one place. The apps are tightly coupled by shared infrastructure, not independently deployable services.

## Consequences
All apps share a single git history. Docker Compose orchestrates everything from the root.
