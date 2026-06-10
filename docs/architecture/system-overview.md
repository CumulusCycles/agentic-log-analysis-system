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

Compose-wired `depends_on` relationships. App-tier and `log-dashboard → ollama` use `condition: service_healthy`; the `log-dashboard → ollama-init` link uses `condition: service_completed_successfully` (one-shot pull); the `ollama-init → ollama` link uses `condition: service_started` (v1.1.2 — see note below).

| Service | Waits for | Gate |
|---|---|---|
| shared-data-api | postgres, mongodb | service_healthy |
| fnol-app | shared-data-api | service_healthy |
| customer-portal | shared-data-api | service_healthy |
| agent-portal | shared-data-api | service_healthy |
| ollama-init | ollama (then pulls `llama3.1:8b` + `nomic-embed-text` and exits) | **service_started** (v1.1.2) |
| log-dashboard | chroma, ollama, ollama-init | service_healthy + service_completed_successfully |

The app-tier dependencies were upgraded as each phase landed a real server with a healthcheck (Phase 3 SDA → postgres/mongodb, Phases 4–6 FNOL/CP/AP → SDA). The `log-dashboard → chroma` link has used `service_healthy` since Phase 2; Phase 8 (ADR-017) added the `ollama` healthy gate and the `ollama-init` completion gate so the dashboard never boots against an unready or model-less Ollama.

**v1.1.2 cold-start fix:** the `ollama-init → ollama` link was `service_healthy` from v1.1.1 through v1.1.1.patch — that combined with v1.1.1's model-aware healthcheck created a cold-start deadlock (ollama can't be healthy without models loaded; ollama-init is what loads them). The gate was flipped to `service_started` so ollama-init starts as soon as the ollama daemon process is up (within seconds — the daemon accepts API calls almost immediately). The dashboard's race protection is preserved at the downstream gate: it still waits for `ollama: service_healthy` AND `ollama-init: service_completed_successfully`, so no chat call fires before both models are loaded.
