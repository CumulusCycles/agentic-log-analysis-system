# ADR-007: Background Claim-Status Simulator

**Status:** Accepted

## Decisions
1. The Shared Data API runs an in-process background task that periodically advances claim statuses through realistic transitions.
2. The simulator is implemented as an `asyncio` task started during FastAPI lifespan startup. No external scheduler container, no separate process.
3. Each status transition is recorded in `claim_status_history` with the assigned adjuster as the actor.
4. Status flow: `submitted → triaged → investigating → settled → closed`, with a terminal `denied` branch reachable from `triaged` or `investigating`.

## Rationale
With Customer Portal and Agent Portal read-only (ADR-005) and FNOL only creating claims, claim statuses would never change at runtime. The dashboard would see static data and no dynamic claim activity in CP/AP logs — defeating the project's core purpose of generating realistic log streams to analyze.

Running the simulator in-process inside the Shared Data API (rather than a separate container) keeps the architecture lean and keeps the simulator's writes on the same connection pool as the rest of the Shared Data API. Recording the assigned adjuster as the actor produces plausible per-agent activity patterns the dashboard can correlate against.

## Consequences
- The simulator's actions appear in `shared-data-api-logs` as normal Shared Data API writes, with `caller=simulator` (not a real app) and `user=<adjuster_id>`.
- Reading Customer Portal or Agent Portal during simulated transitions surfaces dynamic claim activity in their logs, which is what the dashboard ultimately analyzes.
- Tick cadence and transition probabilities are configurable but kept simple — the goal is plausible activity, not modeling real claim handling.
- If the Shared Data API restarts, the simulator restarts with it. Status history persists in Postgres so timeline data survives restarts.
