# ADR-003: Logging Strategy

**Status:** Accepted (amended — see Amendments below)

## Decisions
1. Each app logs in its native format. No common schema is enforced at write time.
2. All four logging apps (Shared Data API, FNOL, Customer Portal, Agent Portal) write logs to named Docker volumes. The dashboard mounts every log volume read-only.

## Rationale
Forcing a normalized log format would reduce realism and eliminate one of the key AI value propositions — the LangGraph agent understanding diverse formats without a custom parser. Real enterprise environments are never uniform.

Persistent volumes ensure logs survive container crashes and restarts. The dashboard reads logs independently without coupling to app containers.

## Consequences
The dashboard handles structlog JSON (Python), Winston JSON (Node), and Logback text (Java). The LangGraph agent receives `raw_text` and handles heterogeneity via LLM understanding.

Seven named volumes: `shared-data-api-logs`, `fnol-logs`, `customer-portal-logs`, `agent-portal-logs` (app logs) plus `postgres-data`, `mongodb-data`, `chroma-data` (data volumes). Never run `docker compose down -v`.

## Amendment — Shared Data API promoted to log-volume writer (ADR-005)

**Date:** Pre-Phase-3 architecture pivot
**Supersedes within this ADR:** Decision 2 (original wording — see [ADR-005](ADR-005-shared-data-api-as-sole-data-layer.md))

As originally written, Decision 2 listed only FNOL, Customer Portal, and Agent Portal as log-volume writers — the Shared Data API logged to stdout only. [ADR-005](ADR-005-shared-data-api-as-sole-data-layer.md) promoted SDA to a log-volume writer because per-request `caller=<app>` and `user=<id>` attribution makes its log stream the dashboard's richest correlation source. The 7th named log volume `shared-data-api-logs` landed in the same pivot and is mounted read-only by the dashboard alongside the other three.
