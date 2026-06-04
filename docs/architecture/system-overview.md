# System Overview

## Container Topology

All eight containers share the `insurance-net` bridge network. Browser traffic
enters via host ports; container-to-container traffic uses internal ports.

```mermaid
graph LR
    Browser((Browser))

    subgraph net["insurance-net (bridge)"]
        SDA["shared-data-api<br/>:8000"]
        FNOL["fnol-app<br/>:8000"]
        CP["customer-portal<br/>:3000"]
        AP["agent-portal<br/>:8080"]
        DASH["log-dashboard<br/>:4000"]

        PG[("postgres<br/>:5432")]
        MG[("mongodb<br/>:27017")]
        CR[("chroma<br/>:8000")]
    end

    Browser -- "host :8002" --> SDA
    Browser -- "host :8001" --> FNOL
    Browser -- "host :3001" --> CP
    Browser -- "host :8081" --> AP
    Browser -- "host :4001" --> DASH

    FNOL --> SDA
    CP --> SDA
    AP --> SDA
    SDA --> PG
    SDA --> MG
    DASH --> CR
```

## Log Flow

All four logging apps write to their own named volumes. The dashboard mounts
every log volume **read-only**, watches them with `watchdog`, embeds new
entries into Chroma, and serves analysis through the LangGraph agent.

```mermaid
graph TB
    SDA[shared-data-api] -- writes --> SV[("shared-data-api-logs")]
    FNOL[fnol-app] -- writes --> FV[("fnol-logs")]
    CP[customer-portal] -- writes --> CV[("customer-portal-logs")]
    AP[agent-portal] -- writes --> AV[("agent-portal-logs")]

    SV -. read-only mount .-> DASH[log-dashboard]
    FV -. read-only mount .-> DASH
    CV -. read-only mount .-> DASH
    AV -. read-only mount .-> DASH

    DASH --> WATCH[watchdog file watcher]
    WATCH --> EMB[OpenAI embeddings]
    EMB --> CHROMA[("chroma vector store")]
    CHROMA --> LG[LangGraph agent]
    LG --> UI[React UI]
```

Shared Data API logs to both stdout and `/app/logs/shared-data-api.log` (volume
`shared-data-api-logs`), which the dashboard also mounts read-only. Every request
line includes `caller=<app>` and `user=<id>` attribution — see ADR-005 and
`docs/tech/logging-strategy.md`.

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

## Startup Dependencies

`docker-compose.yml` wires these `depends_on` relationships so Compose starts services
in a valid order:

| Service | Waits for |
|---|---|
| shared-data-api | postgres (healthy), mongodb (healthy) |
| fnol-app | shared-data-api (healthy) |
| customer-portal | shared-data-api (healthy) |
| agent-portal | shared-data-api (healthy) |
| log-dashboard | chroma (healthy) |

> **Post-Phase-6 state:** every `depends_on` above uses `condition: service_healthy`.
> The app-tier dependencies were upgraded as each phase landed a real server with a
> healthcheck (Phase 3 SDA → postgres/mongodb, Phases 4–6 FNOL/CP/AP → SDA). The
> `log-dashboard → chroma` link has used `service_healthy` since Phase 2.
