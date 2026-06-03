# ADR-003: Logging Strategy

**Status:** Accepted (Decision 2 amended by [ADR-005](ADR-005-shared-data-api-as-sole-data-layer.md))

## Decisions
1. Each app logs in its native format. No common schema is enforced at write time.
2. All four logging apps (Shared Data API, FNOL, Customer Portal, Agent Portal) write logs to named Docker volumes. The dashboard mounts every log volume read-only.

> Note: as originally written, Decision 2 stated the Shared Data API had no log volume. ADR-005 promoted it to a log-volume writer because per-request `caller=<app>` and `user=<id>` attribution makes its log stream the dashboard's richest data source.

## Rationale
Forcing a normalized log format would reduce realism and eliminate one of the key AI value propositions — the LangGraph agent understanding diverse formats without a custom parser. Real enterprise environments are never uniform.

Persistent volumes ensure logs survive container crashes and restarts. The dashboard reads logs independently without coupling to app containers.

## Consequences
The dashboard handles structlog JSON (Python), Winston JSON (Node), and Logback text (Java). The LangGraph agent receives `raw_text` and handles heterogeneity via LLM understanding.

Seven named volumes: `shared-data-api-logs`, `fnol-logs`, `customer-portal-logs`, `agent-portal-logs` (app logs) plus `postgres-data`, `mongodb-data`, `chroma-data` (data volumes). Never run `docker compose down -v`.
