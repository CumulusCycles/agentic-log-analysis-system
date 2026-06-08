# System Overview

Quick-reference data for the running stack: host ports, healthcheck commands, and the startup dependency order. For diagrams and narrative, see the sibling docs:

- [`docker-architecture.html`](docker-architecture.html) — visual rendering of the container topology, volumes, and infrastructure flows. Open in a browser.
- [`system-integration.md`](system-integration.md) — wide-view integration narrative with 11 Mermaid diagrams (data layer, auth, request flows, simulator, X-Source, ingest pipeline, agent, Agitator, chaos).
- [`log-flow.md`](log-flow.md) / [`log-flow.html`](log-flow.html) — deep slice of one log line's journey.

---

## Port Reference

| Container | Internal | Host |
|---|---|---|
| shared-data-api | 8000 | 8002 |
| fnol-app | 8000 | 8001 |
| customer-portal | 3000 | 3001 |
| agent-portal | 8080 | 8081 |
| log-dashboard | 4000 | 4001 |
| postgres | 5432 | 5433 |
| mongodb | 27017 | 27018 |
| chroma | 8000 | internal only |

---

## Healthchecks

| Container | Probe |
|---|---|
| postgres | `pg_isready -U $POSTGRES_USER` |
| mongodb | `mongosh --eval "db.runCommand({ping:1})"` |
| chroma | `bash + /dev/tcp` against `http://localhost:8000/api/v2/heartbeat` (no curl/wget in image) |
| shared-data-api / fnol-app / customer-portal / log-dashboard | HTTP `GET /health` |
| agent-portal | HTTP `GET /actuator/health` |

Full healthcheck rationale + chroma probe internals in [`.claude/rules/infrastructure.md`](../../.claude/rules/infrastructure.md).

---

## Startup Dependencies

Compose-wired `depends_on` relationships. Every relationship below uses `condition: service_healthy` post-Phase-6.

| Service | Waits for |
|---|---|
| shared-data-api | postgres, mongodb |
| fnol-app | shared-data-api |
| customer-portal | shared-data-api |
| agent-portal | shared-data-api |
| log-dashboard | chroma |

The app-tier dependencies were upgraded as each phase landed a real server with a healthcheck (Phase 3 SDA → postgres/mongodb, Phases 4–6 FNOL/CP/AP → SDA). The `log-dashboard → chroma` link has used `service_healthy` since Phase 2.
