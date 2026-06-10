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

Compose-wired `depends_on` relationships. v1.1.2 Option A relaxed the dashboard's chain so it comes up in seconds on cold deploys instead of waiting on the 5–15 min Ollama model pull — full rationale + fix layers documented below the table.

| Service | Waits for | Gate |
|---|---|---|
| shared-data-api | postgres, mongodb | service_healthy |
| fnol-app | shared-data-api | service_healthy |
| customer-portal | shared-data-api | service_healthy |
| agent-portal | shared-data-api | service_healthy |
| ollama-init | ollama (then pulls `llama3.1:8b` + `nomic-embed-text` and exits) | **service_started** (v1.1.2) |
| log-dashboard | chroma | **service_healthy** (fast — chroma starts in ~10s) |
| log-dashboard | ollama | **service_started** (v1.1.2 Option A — daemon process up; model availability checked by the dashboard's own probe + watchdog) |
| log-dashboard | ollama-init | **service_started** (v1.1.2 Option A — ensures the model puller is in the same start batch so selective `up -d log-dashboard` doesn't orphan it; the dashboard does NOT wait on the pull to complete) |

The app-tier dependencies were upgraded as each phase landed a real server with a healthcheck (Phase 3 SDA → postgres/mongodb, Phases 4–6 FNOL/CP/AP → SDA). The `log-dashboard → chroma` link has used `service_healthy` since Phase 2; Phase 8 (ADR-017) added the `ollama` healthy gate and the `ollama-init` completion gate so the dashboard never booted against an unready or model-less Ollama — but that combined with v1.1.1's model-aware healthcheck to create a cold-start chain that left log-dashboard in `Created` for the full 5–15 min model pull.

**v1.1.2 fix layers — read in order:**

1. **Deadlock fix (commit `4c037ba`):** the `ollama-init → ollama` link was `service_healthy` from v1.1.1; combined with v1.1.1's model-aware healthcheck, `ollama` could never be healthy without models loaded AND `ollama-init` is what loads them → deadlock. Flipped to `service_started` so `ollama-init` starts as soon as the daemon process is up. Confirmed by commit message + `4c037ba`.

2. **Option A (commit `2553045` + `c4fd665`):** Even after the deadlock fix, the dashboard waited on `ollama: service_healthy` + `ollama-init: service_completed_successfully` — so log-dashboard's container still sat in `Created` for the full pull. Option A relaxes both gates to `service_started` and adds a lifespan-level promotion watchdog that re-probes Ollama for model availability every 30s (`DASHBOARD_EMBEDDINGS_PROMOTION_INTERVAL_SECONDS`); when both models become available the watchdog wires up the vectorstore + rebuilds the agent graph + kicks off backfill. `/api/status` surfaces `embeddings_state: ready | loading | unreachable` so the frontend can show a friendlier message during the loading window. The `ollama-init: service_started` gate is kept (not dropped) so selective `up -d log-dashboard` doesn't orphan the puller.
