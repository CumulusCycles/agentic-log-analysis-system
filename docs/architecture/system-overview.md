# System Overview

Quick-reference data for the running stack: host ports, healthcheck commands, and the startup dependency order. For diagrams and narrative, see the sibling docs:

- [`site/system-overview.html`](../../site/system-overview.html) — visual rendering of the tables on this page (port grid, healthcheck cards, startup dependency DAG). Open in a browser.
- [`site/docker-architecture.html`](../../site/docker-architecture.html) — visual rendering of the container topology, volumes, and infrastructure flows. Open in a browser.
- [`system-integration.md`](system-integration.md) — wide-view integration narrative with 14 Mermaid diagrams (data layer, auth, request flows, simulator, log volumes, X-Source, ingest pipeline, UI data paths, agent, Agitator, chaos cascade, full circle).
- [`log-flow.md`](log-flow.md) / [`site/log-flow.html`](../../site/log-flow.html) — deep slice of one log line's journey.

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
| ollama | 11434 | internal only (Phase 8 / ADR-017 §6) |
| ollama-init | — | one-shot pull; exits after both models cached |

---

## Healthchecks

| Container | Probe |
|---|---|
| postgres | `pg_isready -U $POSTGRES_USER` |
| mongodb | `mongosh --eval "db.runCommand({ping:1})"` |
| chroma | `bash + /dev/tcp` against `http://localhost:8000/api/v2/heartbeat` (no curl/wget in image) |
| ollama | `ollama list \| awk` checks BOTH `llama3.1:8b` + `nomic-embed-text` are loaded (CMD-SHELL — v1.1.1 tightened the daemon-only check that pre-existed in Phase 8 / ADR-017; `start_period: 900s` covers ollama-init's worst-case cold-pull window). |
| shared-data-api / fnol-app / customer-portal / log-dashboard | HTTP `GET /health` |
| agent-portal | HTTP `GET /actuator/health` |

Full healthcheck rationale + chroma probe internals in [`.claude/rules/infrastructure.md`](../../.claude/rules/infrastructure.md).

---

## Startup Dependencies

Compose-wired `depends_on` relationships. Every `service_healthy` relationship below uses `condition: service_healthy`; the `ollama-init` link uses `condition: service_completed_successfully` since it's a one-shot pull.

| Service | Waits for |
|---|---|
| shared-data-api | postgres, mongodb |
| fnol-app | shared-data-api |
| customer-portal | shared-data-api |
| agent-portal | shared-data-api |
| ollama-init | ollama (then pulls `llama3.1:8b` + `nomic-embed-text` and exits) |
| log-dashboard | chroma, ollama, ollama-init |

The app-tier dependencies were upgraded as each phase landed a real server with a healthcheck (Phase 3 SDA → postgres/mongodb, Phases 4–6 FNOL/CP/AP → SDA). The `log-dashboard → chroma` link has used `service_healthy` since Phase 2; Phase 8 (ADR-017) added the `ollama` healthy gate and the `ollama-init` completion gate so the dashboard never boots against an unready or model-less Ollama.
