# ADR-003: Logging Strategy

**Status:** Accepted

## Decisions
1. Each app logs in its native format. No common schema is enforced at write time.
2. The three logging apps (FNOL, Customer Portal, Agent Portal) write logs to named Docker volumes. The dashboard mounts all three log volumes read-only. The Shared Data API is a pure DB CRUD service and has no log volume.

## Rationale
Forcing a normalized log format would reduce realism and eliminate one of the key AI value propositions — the LangGraph agent understanding diverse formats without a custom parser. Real enterprise environments are never uniform.

Persistent volumes ensure logs survive container crashes and restarts. The dashboard reads logs independently without coupling to app containers.

## Consequences
The dashboard handles structlog JSON (Python), Winston JSON (Node), and Logback text (Java). The LangGraph agent receives `raw_text` and handles heterogeneity via LLM understanding.

Six named volumes: `fnol-logs`, `customer-portal-logs`, `agent-portal-logs` (app logs) plus `postgres-data`, `mongodb-data`, `chroma-data` (data volumes). Never run `docker compose down -v`.
